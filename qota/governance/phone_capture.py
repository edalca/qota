"""Document adapters and permission-checked, read-only capture helpers."""

import frappe
from frappe import _

from qota.phones import PhoneError, region_catalog, validate_international_for_region, validate_phone, validate_region

INVALID_PHONE = "The telephone number is not valid for the selected country. Correct the number or leave the field empty to continue."


def validate_document_phone(doc, legacy, region, national, e164, allow_unstructured_unchanged=False):
	if legacy == national:
		# A single national source is validated without rewriting its stored value.
		try:
			if doc.get(legacy):
				parsed = validate_phone(doc.get(region), doc.get(legacy))
				doc.set(e164, parsed.e164)
			else:
				if doc.get(region):
					validate_region(doc.get(region))
				doc.set(e164, None)
		except PhoneError:
			frappe.throw(_(INVALID_PHONE))
		return
	previous = doc.get_doc_before_save()
	raw, number = doc.get(legacy), doc.get(national)
	old_number = previous.get(national) if previous else None
	# An explicit deletion of a structured capture also deletes its legacy projection.
	if previous and old_number and not number and raw == previous.get(legacy):
		raw = None
	# Legacy clients can still correct the legacy field with an explicit region.
	if previous and raw != previous.get(legacy) and number == old_number:
		number = None
	if not number and not raw:
		doc.set(legacy, None)
		doc.set(national, None)
		doc.set(e164, None)
		if doc.get(region):
			try:
				validate_region(doc.get(region))
			except PhoneError:
				frappe.throw(_(INVALID_PHONE))
		return
	if allow_unstructured_unchanged and previous and not any(previous.get(f) for f in (region, national, e164)):
		if all(doc.get(f) == previous.get(f) for f in (legacy, region, national, e164)):
			return
	try:
		candidate = number if number else raw
		if not number and isinstance(candidate, str) and candidate.startswith("+"):
			parsed = validate_international_for_region(doc.get(region), candidate)
		else:
			parsed = validate_phone(doc.get(region), candidate)
	except PhoneError:
		frappe.throw(_(INVALID_PHONE))
	doc.set(region, parsed.region)
	doc.set(national, parsed.national)
	doc.set(e164, parsed.e164)
	unchanged_source = previous and all(doc.get(f) == previous.get(f) for f in (legacy, region, national))
	if not unchanged_source:
		doc.set(legacy, parsed.national if legacy == "primary_phone" else parsed.e164)


@frappe.whitelist(methods=["POST"])
def capture_options(doctype):
	if doctype not in ("Subscriber", "Institutional Settings"):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	frappe.has_permission(doctype, "read", throw=True)
	return dict(regions=region_catalog(frappe.local.lang),
		default_region=frappe.db.get_single_value("Institutional Settings", "default_phone_region") or "")


@frappe.whitelist(methods=["POST"])
def inspect_capture(doctype, name):
	if doctype not in ("Subscriber",):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	from qota.phones import stored_phone
	try:
		stored_phone(doc)
		return dict(status="Valid")
	except PhoneError as exc:
		return dict(status="Missing" if str(exc) == "missing_phone" else "Invalid", reason_code=str(exc))


@frappe.whitelist(methods=["POST"])
def preview_capture(doctype, region, national):
	if doctype not in ("Subscriber",):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	frappe.has_permission(doctype, "write", throw=True)
	try:
		return dict(status="Valid", e164=validate_phone(region, national).e164)
	except PhoneError as exc:
		return dict(status="Invalid", reason_code=str(exc))
