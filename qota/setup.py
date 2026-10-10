# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""Install and remove Qota customizations on official DocTypes.

The official apps are not edited. Fields, titles, and list columns are applied
from here on install and on every migrate, and removed on uninstall.
"""

import json

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ABBREVIATION_LENGTH = 10


def after_install():
	"""Create the custom fields, titles, and list view once the target DocTypes exist."""
	custom_fields = get_custom_fields()
	if not custom_fields:
		return

	create_custom_fields(custom_fields, ignore_validate=True)

	if "WA Account" in custom_fields:
		set_title_field("WA Account", "account_name")
		set_property_dynamic("WA Account", "account_name", "label", "Junta Name", "Data")
		configure_list_view(
			"WA Account",
			["account_name", "qota_abbreviation", "qota_phone_number", "status"],
		)
		# The status indicator is drawn before the other columns unless the
		# list settings name this order.
		configure_list_columns(
			"WA Account",
			[
				{"fieldname": "account_name", "label": "Junta Name"},
				{"fieldname": "qota_abbreviation", "label": "Abbreviation"},
				{"fieldname": "qota_phone_number", "label": "Phone Number"},
				{"fieldname": "status_field", "label": "Status"},
			],
		)

	frappe.db.commit()
	for doctype in custom_fields:
		frappe.clear_cache(doctype=doctype)


def before_uninstall():
	"""Remove the custom fields and property setters added by this app."""
	delete_custom_fields(get_custom_fields())
	delete_app_property_setters(["WA Account"])
	if frappe.db.exists("DocType", "List View Settings") and frappe.db.exists(
		"List View Settings", "WA Account"
	):
		frappe.delete_doc("List View Settings", "WA Account", ignore_permissions=True, force=True)
	frappe.db.commit()


def validate_wa_account(doc, method=None):
	"""The abbreviation is required and contains at most 10 letters."""
	if not doc.meta.get_field("qota_abbreviation"):
		return
	abbreviation = (doc.qota_abbreviation or "").strip()
	doc.qota_abbreviation = abbreviation
	if not abbreviation.isalpha() or len(abbreviation) > ABBREVIATION_LENGTH:
		frappe.throw(
			_("The abbreviation must be at most {0} letters.").format(ABBREVIATION_LENGTH)
		)
	if doc.meta.get_field("qota_phone_number"):
		doc.qota_phone_number = (doc.qota_phone_number or "").strip()


def get_custom_fields():
	"""Custom fields placed with insert_after so the official DocType files stay untouched."""
	fields = {
		"WA Account": [
			{
				"fieldname": "qota_abbreviation",
				"label": "Abbreviation",
				"fieldtype": "Data",
				"insert_after": "account_name",
				"reqd": 1,
				"length": ABBREVIATION_LENGTH,
				"in_list_view": 1,
				"translatable": 0,
				"description": "Up to 10 letters.",
			},
			{
				"fieldname": "qota_phone_number",
				"label": "Phone Number",
				"fieldtype": "Data",
				"options": "Phone",
				"insert_after": "phone_id",
				"in_list_view": 1,
				"translatable": 0,
				"description": "The telephone number of this line. Phone ID is the Meta identifier.",
			},
		],
		"WA Profile": [
			{
				"fieldname": "qota_last_seen",
				"label": "Last Seen",
				"fieldtype": "Datetime",
				"insert_after": "profile_name",
				"hidden": 1,
				"read_only": 1,
				"no_copy": 1,
			}
		],
	}
	return {doctype: rows for doctype, rows in fields.items() if frappe.db.exists("DocType", doctype)}


def delete_custom_fields(custom_fields):
	"""Delete the custom field rows for the fields this app added."""
	for doctype, fields in custom_fields.items():
		frappe.db.delete(
			"Custom Field",
			{
				"fieldname": ("in", [field["fieldname"] for field in fields]),
				"dt": doctype,
			},
		)


def delete_app_property_setters(doctypes):
	"""Remove title and list-view property setters for these DocTypes."""
	for doctype in doctypes:
		frappe.db.delete("Property Setter", {"doc_type": doctype})


def configure_list_view(doctype, fields_to_show):
	"""Show only the named fields in the list. Every other field is hidden there."""
	standard_fields = frappe.get_all("DocField", filters={"parent": doctype}, pluck="fieldname")
	custom_fields = frappe.get_all("Custom Field", filters={"dt": doctype}, pluck="fieldname")
	for fieldname in set(standard_fields + custom_fields):
		is_visible = 1 if fieldname in fields_to_show else 0
		set_property_dynamic(doctype, fieldname, "in_list_view", is_visible, "Check")


def configure_list_columns(doctype, columns):
	"""Store the list column order, including the status indicator."""
	wanted = [row["fieldname"] for row in columns]
	if frappe.db.exists("List View Settings", doctype):
		doc = frappe.get_doc("List View Settings", doctype)
		try:
			current = [row.get("fieldname") for row in json.loads(doc.fields or "[]")]
		except ValueError:
			current = []
		if current == wanted:
			return
		doc.fields = json.dumps(columns)
		doc.save(ignore_permissions=True)
		return
	doc = frappe.new_doc("List View Settings")
	doc.name = doctype
	doc.fields = json.dumps(columns)
	doc.insert(ignore_permissions=True)


def set_title_field(doctype, fieldname):
	"""Set the title field. The list uses it as the first column."""
	set_property_dynamic(doctype, None, "title_field", fieldname, "Data")


def set_property_dynamic(doctype, fieldname, property, value, property_type):
	"""Create or update one property setter on a DocType or on one of its fields."""
	if fieldname:
		ps_name = f"{doctype}-{fieldname}-{property}"
		doctype_or_field = "DocField"
	else:
		ps_name = f"{doctype}-main-{property}"
		doctype_or_field = "DocType"

	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value)
		return

	frappe.make_property_setter(
		{
			"doctype": doctype,
			"doctype_or_field": doctype_or_field,
			"fieldname": fieldname,
			"property": property,
			"value": value,
			"property_type": property_type,
		},
		ignore_validate=True,
	)
