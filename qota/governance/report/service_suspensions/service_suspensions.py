# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

OPERATIONAL_STATUSES = ("Scheduled", "Executed", "Cancelled")


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	summary = get_report_summary(data)
	return columns, data, None, None, summary


def get_columns():
	return [
		{
			"label": _("Suspension"),
			"fieldname": "suspension",
			"fieldtype": "Link",
			"options": "Service Suspension",
			"width": 140,
		},
		{
			"label": _("Subscriber Name"),
			"fieldname": "full_name",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Sector"),
			"fieldname": "sector",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("Block"),
			"fieldname": "block",
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"label": _("House No."),
			"fieldname": "house_number",
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"label": _("Contract"),
			"fieldname": "service_contract",
			"fieldtype": "Link",
			"options": "Service Contract",
			"width": 120,
		},
		{
			"label": _("Suspension Reason"),
			"fieldname": "suspension_type",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Effective Date"),
			"fieldname": "effective_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Executed Date"),
			"fieldname": "executed_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Outstanding"),
			"fieldname": "outstanding",
			"fieldtype": "Currency",
			"width": 120,
		},
	]


def _to_int(value):
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def row_status(suspension):
	# Cancel writes the status back to Draft and sets docstatus to 2.
	if suspension.docstatus == 2:
		return "Cancelled"
	return suspension.status


def suspension_filters(status_filter, suspension_type_filter):
	filters = {}
	if suspension_type_filter:
		filters["suspension_type"] = suspension_type_filter

	if status_filter == "Cancelled":
		filters["docstatus"] = 2
	elif status_filter == "Draft":
		filters["docstatus"] = 0
		filters["status"] = "Draft"
	elif status_filter in ("Scheduled", "Executed"):
		filters["docstatus"] = 1
		filters["status"] = status_filter
	else:
		filters["docstatus"] = ["in", [1, 2]]
	return filters


def get_data(filters):
	filters = filters or {}
	status_filter = filters.get("status") or "All"
	suspension_type_filter = filters.get("suspension_type")
	premises_filter = filters.get("premises")

	suspensions = frappe.get_all(
		"Service Suspension",
		filters=suspension_filters(status_filter, suspension_type_filter),
		fields=[
			"name",
			"full_name",
			"service_contract",
			"subscriber",
			"premises",
			"suspension_type",
			"status",
			"docstatus",
			"effective_date",
			"executed_date",
		],
		order_by="effective_date asc",
	)

	if not suspensions:
		return []

	premises_names = list({s.premises for s in suspensions if s.premises})
	premises_map = {}
	if premises_names:
		premises_list = frappe.get_all(
			"Premises",
			filters={"name": ["in", premises_names]},
			fields=["name", "sector", "block", "house_number"],
		)
		premises_map = {p.name: p for p in premises_list}

	contract_names = list({s.service_contract for s in suspensions if s.service_contract})
	outstanding_map = {}
	if contract_names:
		debt_entries = frappe.get_all(
			"Debt Ledger Entry",
			filters={
				"service_contract": ["in", contract_names],
				"entry_type": "Monthly Fee",
				"outstanding_amount": [">", 0],
				"docstatus": ["!=", 2],
			},
			fields=["service_contract", "outstanding_amount"],
		)
		for entry in debt_entries:
			cid = entry.service_contract
			outstanding_map[cid] = outstanding_map.get(cid, 0) + flt(entry.outstanding_amount)

	rows = []
	for s in suspensions:
		p = premises_map.get(s.premises, frappe._dict())
		if premises_filter and s.premises != premises_filter:
			continue

		status = row_status(s)
		rows.append(
			{
				"suspension": s.name,
				"full_name": s.full_name,
				"status": _(status),
				"status_key": status,
				"sector": p.get("sector") or "-",
				"block": _to_int(p.get("block")),
				"house_number": _to_int(p.get("house_number")),
				"service_contract": s.service_contract,
				"suspension_type": _(s.suspension_type) if s.suspension_type else "",
				"effective_date": s.effective_date,
				"executed_date": s.executed_date,
				"outstanding": outstanding_map.get(s.service_contract, 0),
			}
		)

	rows.sort(key=lambda r: (r["block"] or 0, r["house_number"] or 0))
	return rows


def get_report_summary(data):
	if not data:
		return []

	counts = {status: 0 for status in OPERATIONAL_STATUSES}
	for row in data:
		if row["status_key"] in counts:
			counts[row["status_key"]] += 1

	return [
		{
			"value": counts["Scheduled"],
			"label": _("Scheduled"),
			"datatype": "Int",
			"indicator": "Orange",
		},
		{
			"value": counts["Executed"],
			"label": _("Executed"),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"value": counts["Cancelled"],
			"label": _("Cancelled"),
			"datatype": "Int",
			"indicator": "Gray",
		},
		{
			"value": sum(r["outstanding"] for r in data),
			"label": _("Total Outstanding"),
			"datatype": "Currency",
			"indicator": "Red",
		},
	]
