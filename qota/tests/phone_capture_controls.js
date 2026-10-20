// Focused functional tests for the shared standard Frappe telephone controls.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const fields = { legacy: "legacy", region: "region", national: "national", e164: "e164" };
const calls = [];
let nextResponse = {};
const context = {
	qota: {}, __: (text, args) => args ? text.replace("{0}", args[0]) : text,
	frappe: { provide() {}, msgprint() {}, call: async (call) => { calls.push(call); return { message: nextResponse }; } },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync("qota/public/js/phone_capture.js", "utf8"), context);
const api = context.qota.phone_capture;
function form(doc, isNew) {
	const values = [], properties = [], alerts = [], events = {};
	return {
		doc, doctype: "Subscriber", docname: "Synthetic", fields_dict: { national: { $input: { attr() { return this; }, off() { return this; }, on(name, fn) { events[name] = fn; return this; } } } },
		is_new: () => isNew, set_value: async (name, value) => { values.push([name, value]); doc[name] = value; },
		set_df_property: (...args) => properties.push(args), add_custom_button() {},
		dashboard: { clear_headline() {}, set_headline_alert: (...args) => alerts.push(args) },
		values, properties, alerts, events,
	};
}
(async () => {
	nextResponse = { regions: [{ value: "HN", label: "Honduras (+504)" }], default_region: "HN" };
	const historical = form({ legacy: "123456789", region: null }, false);
	await api.setup(historical, fields);
	assert.equal(historical.values.length, 0);
	assert.equal(historical.properties[0][2][1].value, "HN");
	const fresh = form({}, true); await api.setup(fresh, fields); assert.equal(fresh.doc.region, "HN");
	const foreign = form({ region: "CA" }, true); await api.setup(foreign, fields); assert.equal(foreign.values.length, 0);
	nextResponse = { status: "Invalid", reason_code: "missing_region" };
	await api.warning(historical, fields); assert.equal(historical.values.length, 0); assert.equal(historical.alerts.length, 1);
	nextResponse = { status: "Missing" }; const empty = form({}, false); await api.warning(empty, fields); assert.equal(empty.alerts.length, 0);
	nextResponse = { status: "Valid", e164: "+12015550123" };
	fresh.doc.national = "2015550123"; fresh.doc.region = "US";
	const prior = fresh.values.length; await api.preview(fresh, fields); assert.equal(fresh.values.length, prior); assert.equal(fresh.doc.e164, undefined);
	assert.equal(fresh.properties.at(-1)[2], "International preview: +12015550123");
	let prevented = false;
	historical.events["beforeinput.qota-phone"]({ originalEvent: { data: "١" }, preventDefault() { prevented = true; } }); assert.ok(prevented);
	prevented = false;
	historical.events["paste.qota-phone"]({ originalEvent: { clipboardData: { getData: () => "123-456" } }, preventDefault() { prevented = true; } }); assert.ok(prevented);
	prevented = false;
	historical.events["beforeinput.qota-phone"]({ originalEvent: { data: "0" }, preventDefault() { prevented = true; } }); assert.ok(!prevented);
	assert.ok(calls.every(call => call.type === "POST"));
	const singleFields = { legacy: "primary_phone", region: "region", national: "primary_phone", e164: "e164" };
	nextResponse = { regions: [{ value: "HN", label: "Honduras (+504)" }], default_region: "HN" };
	const original = form({ primary_phone: "123456789" }, false);
	await api.setup(original, singleFields);
	assert.equal(original.doc.primary_phone, "123456789");
	assert.equal(original.values.length, 0);
	const newSingle = form({}, true);
	await api.setup(newSingle, singleFields);
	assert.equal(newSingle.doc.region, "HN");
	const newCapture = form({}, false);
	await api.setup(newCapture, singleFields);
	assert.equal(newCapture.values.length, 0);
	newCapture.doc.primary_phone = "2015550123";
	nextResponse = { status: "Invalid" };
	await api.preview(newCapture, singleFields);
	assert.equal(newCapture.doc.region, "HN");
	assert.equal(newCapture.doc.primary_phone, "2015550123");
	console.log("Shared capture controls: 16 functional checks passed, including the single primary_phone source.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
