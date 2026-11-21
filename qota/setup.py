# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""Install and update Qota navigation customizations."""

import frappe


# Same properties as the Operations link in subscribers.json.
WATER_ISSUE_REPORT_LINK = dict(
	type='Link',
	label='Water Issue Report',
	link_type='DocType',
	link_to='Water Issue Report',
	child=1,
	indent=0,
	icon='clipboard',
	hidden=0,
	open_in_new_tab=1,
)
_LINK_CHECK_FIELDS = ('child', 'indent', 'hidden', 'open_in_new_tab')


def after_install():
	"""Ensure Qota navigation links and titles are applied after install or migrate."""
	ensure_navigation()
	frappe.db.commit()


def _is_water_issue_report_link(row):
	return row.link_type == 'DocType' and row.link_to == 'Water Issue Report'


def _operations_child_end(items):
	section = next((index for index, row in enumerate(items)
		if row.type == 'Section Break' and row.label == 'Operations'), None)
	if section is None:
		return None
	end = section + 1
	while end < len(items) and items[end].child:
		end += 1
	return section, end


def _water_issue_link_matches(row):
	for field, value in WATER_ISSUE_REPORT_LINK.items():
		current = row.get(field)
		if field in _LINK_CHECK_FIELDS:
			current = int(current or 0)
		if current != value:
			return False
	return True


def _ensure_water_issue_report_link(doc):
	"""Keep one Water Issue Report link inside Operations. Return True when changed."""
	bounds = _operations_child_end(doc.items)
	if bounds is None:
		return False
	section, end = bounds
	links = [row for row in doc.items if _is_water_issue_report_link(row)]
	inside = [row for row in links if section < doc.items.index(row) < end]
	if len(links) == 1 and inside and _water_issue_link_matches(links[0]):
		return False
	for row in links:
		doc.remove(row)
	bounds = _operations_child_end(doc.items)
	if bounds is None:
		return False
	_section, end = bounds
	doc.append('items', dict(WATER_ISSUE_REPORT_LINK), position=end)
	return True


def ensure_navigation():
	if frappe.db.exists('Sidebar', 'Subscribers'):
		doc = frappe.get_doc('Sidebar', 'Subscribers')
		changed = _ensure_water_issue_report_link(doc)
		matching = [r for r in doc.items if r.link_type == 'DocType' and r.link_to == 'Institutional Settings']
		if not matching:
			doc.append('items', dict(type='Link', label='Governance Settings', link_type='DocType',
				link_to='Institutional Settings', child=0, indent=0, icon='settings', open_in_new_tab=1))
			changed = True
		if changed:
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
