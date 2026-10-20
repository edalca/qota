# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""Install and update Qota navigation customizations."""

import frappe


def after_install():
	"""Ensure Qota navigation links and titles are applied after install or migrate."""
	ensure_navigation()
	frappe.db.commit()


def ensure_navigation():
	if frappe.db.exists('Sidebar', 'Subscribers'):
		doc = frappe.get_doc('Sidebar', 'Subscribers')
		matching = [r for r in doc.items if r.link_type == 'DocType' and r.link_to == 'Institutional Settings']
		if not matching:
			doc.append('items', dict(type='Link', label='Governance Settings', link_type='DocType',
				link_to='Institutional Settings', child=0, indent=0, icon='settings', open_in_new_tab=1))
			_save_navigation(doc)
	if frappe.db.exists('Dock', 'qota'):
		doc = frappe.get_doc('Dock', 'qota')
		changed = False
		for row in doc.items:
			if row.link_type == 'Sidebar' and row.link_to == 'Subscribers' and row.title == 'Subscribers':
				row.title = 'Governance'
				changed = True
		if changed:
			_save_navigation(doc)


def _save_navigation(doc):
	"""Setup updates installed navigation, never exports a site's layout to source."""
	previous = frappe.flags.in_import
	frappe.flags.in_import = True
	try:
		doc.save(ignore_permissions=True)
	finally:
		frappe.flags.in_import = previous
