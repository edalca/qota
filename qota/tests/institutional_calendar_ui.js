// Run with node --test qota/tests/institutional_calendar_ui.js.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const context = {
	frappe: {
		ui: { form: { on() {} } }, provide() {},
		throw(message) { throw new Error(message); },
	}, qota: { governance: {} }, __: (text) => text,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync("qota/governance/doctype/institutional_settings/institutional_settings.js", "utf8"), context);
const Editor = context.qota.governance.OfficeCalendarEditor;
const normalize = (kind, values) => JSON.parse(JSON.stringify(Editor.normalize(kind, values)));

test("holiday needs only a date and clears all reasons and intervals", () => {
	assert.deepEqual(normalize("Holiday", { exception_date: "2026-11-02", internal_reason: "ignored", public_reason: "ignored" }), {
		exception: { exception_date: "2026-11-02", exception_type: "Holiday", day_status: "Closed", internal_reason: "", public_reason: "" }, interval: null,
	});
});

test("replacement hours normalize one interval and retain only the internal reason", () => {
	const result = normalize("Exceptional Hours", { exception_date: "2026-12-24", start_time: "8:00", end_time: "12:00:00", internal_reason: " Private ", public_reason: "ignored" });
	assert.deepEqual(result.interval, { exception_date: "2026-12-24", start_time: "08:00:00", end_time: "12:00:00" });
	assert.equal(result.exception.day_status, "Open");
	assert.equal(result.exception.internal_reason, "Private");
	assert.equal(result.exception.public_reason, "");
});

test("extraordinary closure requires an internal reason and never creates intervals", () => {
	assert.throws(() => normalize("Extraordinary Closure", { exception_date: "2026-12-31", internal_reason: " " }));
	const result = normalize("Extraordinary Closure", { exception_date: "2026-12-31", internal_reason: "Private", start_time: "8:00", end_time: "12:00" });
	assert.equal(result.exception.day_status, "Closed");
	assert.equal(result.interval, null);
});

test("strict dates, legacy types, missing reasons and invalid intervals fail before mutation", () => {
	for (const exception_date of ["2026-02-29", "2026-02-30", "0000-01-01", "2026-13-01", "2026-00-10", "bad"]) {
		assert.throws(() => normalize("Holiday", { exception_date }));
	}
	assert.equal(normalize("Holiday", { exception_date: "2028-02-29" }).exception.exception_date, "2028-02-29");
	for (const kind of ["Administrative Meeting", "Special Day"]) assert.throws(() => normalize(kind, { exception_date: "2026-10-20" }));
	const base = { exception_date: "2026-10-20", internal_reason: "Private" };
	for (const [start_time, end_time] of [["08:00", "08:00"], ["22:00", "02:00"], ["24:00", "25:00"], ["8:0", "12:00"], ["08:00:60", "12:00"], [null, "12:00"]]) {
		assert.throws(() => normalize("Exceptional Hours", { ...base, start_time, end_time }));
	}
	assert.throws(() => normalize("Exceptional Hours", { ...base, start_time: "08:00", end_time: "12:00", internal_reason: "" }));
});

test("upcoming projection uses only the server date, sorts and preserves historical rows", () => {
	const doc = { calendar_exceptions: [{ exception_date: "2026-12-24" }, { exception_date: "2026-10-17" }, { exception_date: "2026-10-18" }] };
	const before = JSON.stringify(doc);
	assert.deepEqual(Array.from(Editor.upcoming(doc, "2026-10-18"), (row) => row.exception_date), ["2026-10-18", "2026-12-24"]);
	assert.equal(JSON.stringify(doc), before);
	assert.equal(Editor.format_date("2026-11-02"), "02/11/2026");
	assert.equal(Editor.upcoming(doc, "2027-01-01").length, 0);
	assert.deepEqual(Array.from(Editor.types, (type) => type.value), ["Holiday", "Exceptional Hours", "Extraordinary Closure"]);
});
