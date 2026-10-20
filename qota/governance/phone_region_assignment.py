"""Explicit, atomic historical region assignment with aggregate native audit."""

import hashlib
import json
import re
import uuid

import frappe
from frappe import _

from qota.phones import PhoneError, stored_phone, validate_region

SETTINGS = "Institutional Settings"
NOTICE = "Assigning a region does not prove ownership, actual location or activity of a telephone line. Original telephone values, including invalid numbers, will be preserved."


def _authorize():
	frappe.only_for("System Manager")
	for doctype in (SETTINGS, "Subscriber"):
		for permission in ("read", "write"):
			frappe.has_permission(doctype, permission, throw=True)


def _region(lock=False):
	rows = frappe.db.sql("SELECT value FROM tabSingles WHERE doctype=%s AND field='default_phone_region'" + (" FOR UPDATE" if lock else ""), (SETTINGS,))
	try:
		return validate_region(rows[0][0] if rows else None)
	except PhoneError:
		frappe.throw(_("Save a supported default telephone region before reviewing historical numbers."))


def _pending(lock=False):
	return frappe.db.sql("""SELECT name, modified, primary_phone, primary_phone_region,
		primary_phone_e164 FROM tabSubscriber
		WHERE COALESCE(primary_phone,'') != ''
		AND COALESCE(primary_phone_region,'') = '' ORDER BY name""" + (" FOR UPDATE" if lock else ""), as_dict=True)


def _summary(rows, region):
	valid = 0
	for row in rows:
		candidate = dict(row, primary_phone_region=region)
		try:
			stored_phone(candidate)
			valid += 1
		except PhoneError:
			pass
	return dict(region=region, eligible=len(rows), valid=valid, invalid=len(rows)-valid)


def _fingerprint(rows, region):
	# Only this one-way digest is retained; no auxiliary telephone list is stored.
	return hashlib.sha256(json.dumps([region, rows], sort_keys=True, default=str).encode()).hexdigest()


@frappe.whitelist(methods=["POST"])
def preview_assignment():
	_authorize()
	region = _region()
	rows = _pending()
	token = uuid.uuid4().hex
	frappe.cache.set_value("qota-phone-region-preview:" + token,
		dict(user=frappe.session.user, region=region, fingerprint=_fingerprint(rows, region)), expires_in_sec=600)
	return dict(_summary(rows, region), token=token, warning=_(NOTICE))


@frappe.whitelist(methods=["POST"])
def apply_assignment(token, confirmed=False):
	_authorize()
	if confirmed not in (True, 1, "1") or not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
		frappe.throw(_("Explicit confirmation of the historical region assignment is required."))
	with frappe.cache.lock("qota-phone-region-assignment", timeout=120, blocking_timeout=5):
		key = "qota-phone-region-preview:" + token
		preview = frappe.cache.get_value(key)
		audit_name = "qota-phone-region-" + token
		if frappe.db.exists("Version", audit_name):
			audit = frappe.get_doc("Version", audit_name)
			data = json.loads(audit.data)["phone_region_assignment"]
			if data["actor"] != frappe.session.user:
				frappe.throw(_("Not permitted."), frappe.PermissionError)
			return dict(data["result"], repeated=True)
		if not preview or preview["user"] != frappe.session.user:
			frappe.throw(_("The review has expired. Review the historical numbers again."))
		region = _region(lock=True)
		rows = _pending(lock=True)
		if region != preview["region"] or _fingerprint(rows, region) != preview["fingerprint"]:
			frappe.throw(_("The configuration or eligible records changed. Review the historical numbers again."))
		result = _summary(rows, region)
		for row in rows:
			# This exceptional administrative operation never invokes Subscriber.save().
			frappe.db.sql("UPDATE tabSubscriber SET primary_phone_region=%s WHERE name=%s AND COALESCE(primary_phone_region,'')=''", (region, row.name))
		for row in rows:
			actual = frappe.db.get_value("Subscriber", row.name,
				["primary_phone", "primary_phone_e164", "primary_phone_region"], as_dict=True)
			if any(actual.get(f) != row.get(f) for f in ("primary_phone", "primary_phone_e164")) or actual.primary_phone_region != region:
				frappe.throw(_("Historical region assignment verification failed."))
		result.update(assigned=len(rows), remaining=len(_pending(lock=True)))
		frappe.get_doc(dict(doctype="Version", name=audit_name, ref_doctype=SETTINGS, docname=SETTINGS,
			data=json.dumps(dict(phone_region_assignment=dict(actor=frappe.session.user,
				at=str(frappe.utils.now_datetime()), region=region, result=result))))).db_insert()
		return result
