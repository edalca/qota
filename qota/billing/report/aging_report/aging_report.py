# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Contract"), "fieldname": "contract", "fieldtype": "Link", "options": "Service Contract", "width": 120},
		{"label": _("Subscriber Name"), "fieldname": "subscriber_name", "fieldtype": "Data", "width": 180},
		{"label": _("Location"), "fieldname": "location", "fieldtype": "Data", "width": 140},
		{"label": _("Total Outstanding"), "fieldname": "total_outstanding", "fieldtype": "Currency", "width": 130},
		{"label": _("Current (1-30)"), "fieldname": "range_1", "fieldtype": "Currency", "width": 110},
		{"label": _("31-60 Days"), "fieldname": "range_2", "fieldtype": "Currency", "width": 110},
		{"label": _("61-90 Days"), "fieldname": "range_3", "fieldtype": "Currency", "width": 110},
		{"label": _("91+ Days"), "fieldname": "range_4", "fieldtype": "Currency", "width": 110},
	]


def get_data(filters):
	"""Return outstanding debt grouped by contract and bucketed into aging ranges."""
	report_date = getdate(filters.get("to_date") or nowdate())

	entries = frappe.get_all(
		"Debt Ledger Entry",
		filters={"outstanding_amount": [">", 0], "docstatus": ["!=", 2]},
		fields=["service_contract", "outstanding_amount", "due_date"],
	)
	if not entries:
		return []

	contract_names = list({e.service_contract for e in entries})
	contracts = frappe.get_all(
		"Service Contract",
		filters={"name": ["in", contract_names]},
		fields=["name", "full_name", "premises"],
	)
	contract_map = {c.name: c for c in contracts}

	premises_names = list({c.premises for c in contracts if c.premises})
	premises = frappe.get_all(
		"Premises",
		filters={"name": ["in", premises_names]},
		fields=["name", "block", "house_number"],
	)
	premises_map = {p.name: p for p in premises}

	premises_filter = filters.get("premises")
	grouped_data = {}

	for d in entries:
		contract = contract_map.get(d.service_contract)
		if not contract:
			continue
		if premises_filter and contract.premises != premises_filter:
			continue

		p = premises_map.get(contract.premises, frappe._dict())
		contract_id = d.service_contract

		if contract_id not in grouped_data:
			grouped_data[contract_id] = {
				"contract": contract_id,
				"subscriber_name": contract.full_name,
				"location": _("Block: {0} House: {1}").format(p.get("block"), p.get("house_number")),
				"total_outstanding": 0,
				"range_1": 0,
				"range_2": 0,
				"range_3": 0,
				"range_4": 0,
			}

		amount = flt(d.outstanding_amount)
		grouped_data[contract_id]["total_outstanding"] += amount

		days = date_diff(report_date, d.due_date) if d.due_date else 0

		if days <= 30:
			grouped_data[contract_id]["range_1"] += amount
		elif days <= 60:
			grouped_data[contract_id]["range_2"] += amount
		elif days <= 90:
			grouped_data[contract_id]["range_3"] += amount
		else:
			grouped_data[contract_id]["range_4"] += amount

	return list(grouped_data.values())
