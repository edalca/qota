# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""WhatsApp dock shell for the official module.

The sidebar is titled WhatsApp because that is the official module's name, and
the desk uses that title as the module shell. Qota ships the menu in code. The
official app is not edited, and it does not ship this sidebar.

Custom fields on the official DocTypes live in qota.setup.
"""

import frappe


def ensure_whatsapp_desk():
	"""Create the dock shell once the official app is installed."""
	if not frappe.db.exists("DocType", "WA Settings"):
		return
	if not frappe.db.exists("Module Def", "WhatsApp"):
		return
	if frappe.db.get_value("Module Def", "WhatsApp", "app_name") != "whatsapp":
		return

	_ensure_sidebar()


def _ensure_sidebar():
	previous = frappe.flags.in_import
	frappe.flags.in_import = True
	try:
		if frappe.db.exists("Sidebar", "WhatsApp"):
			doc = frappe.get_doc("Sidebar", "WhatsApp")
		else:
			doc = frappe.new_doc("Sidebar")
			doc.title = "WhatsApp"
			doc.module = "WhatsApp"
		doc.app = "qota"
		doc.module = "WhatsApp"
		doc.standard = 0
		doc.header_icon = "whatsapp-chat-duotone"
		doc.set("items", _items())
		doc.save(ignore_permissions=True)
	finally:
		frappe.flags.in_import = previous


def _items():
	def link(label, link_to, link_type, icon, child=0):
		return {
			"type": "Link",
			"label": label,
			"link_to": link_to,
			"link_type": link_type,
			"icon": icon,
			"child": child,
			"added": 0,
			"hidden": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
			"open_in_new_tab": 1,
			"is_default_module": 0,
		}

	def section(label):
		return {
			"type": "Section Break",
			"label": label,
			"link_type": "DocType",
			"icon": "",
			"child": 0,
			"added": 0,
			"hidden": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
			"open_in_new_tab": 1,
			"is_default_module": 0,
		}

	return [
		link("Conversations", "whatsapp-conversations", "Page", "message-circle"),
		link("WhatsApp Notifications", "WhatsApp Notifications", "DocType", "bell"),
		section("WhatsApp Connection"),
		link("WA Account", "WA Account", "DocType", "smartphone", child=1),
		link("WA Settings", "WA Settings", "DocType", "settings", child=1),
		section("WhatsApp Records"),
		link("WA Message", "WA Message", "DocType", "file-text", child=1),
		link("WA Profile", "WA Profile", "DocType", "contact", child=1),
		link("WA Template", "WA Template", "DocType", "layout-template", child=1),
		link("WA Log", "WA Log", "DocType", "scroll-text", child=1),
	]
