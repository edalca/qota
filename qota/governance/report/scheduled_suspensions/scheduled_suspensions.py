# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


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
			"label": _("Sector"),
			"fieldname": "sector",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("Block"),
			"fieldname": "block",
			"fieldtype": "Data",
			"width": 80,
		},
		{
			"label": _("House No."),
			"fieldname": "house_number",
			"fieldtype": "Data",
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
			"label": _("Suspension Type"),
			"fieldname": "suspension_type",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Reason"),
			"fieldname": "reason",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Effective Date"),
			"fieldname": "effective_date",
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


def get_data(filters):
	filters = filters or {}
	status_filter = filters.get("status") or "Scheduled"
	reason_filter = filters.get("reason")
	premises_filter = filters.get("premises")

	sus_filters = {"status": status_filter, "docstatus": ["!=", 2]}
	if reason_filter:
		sus_filters["reason"] = reason_filter

	suspensions = frappe.get_all(
		"Service Suspension",
		filters=sus_filters,
		fields=[
			"name",
			"full_name",
			"service_contract",
			"subscriber",
			"premises",
			"suspension_type",
			"reason",
			"effective_date",
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

		rows.append({
			"suspension": s.name,
			"full_name": s.full_name,
			"sector": p.get("sector") or "-",
			"block": p.get("block") or "-",
			"house_number": p.get("house_number") or "-",
			"service_contract": s.service_contract,
			"suspension_type": _(s.suspension_type),
			"reason": _(s.reason),
			"effective_date": s.effective_date,
			"outstanding": outstanding_map.get(s.service_contract, 0),
		})

	return rows


def get_report_summary(data):
	if not data:
		return []

	return [
		{
			"value": len(data),
			"label": _("Scheduled Suspensions"),
			"datatype": "Int",
			"indicator": "Orange",
		},
		{
			"value": sum(r["outstanding"] for r in data),
			"label": _("Total Outstanding"),
			"datatype": "Currency",
			"indicator": "Red",
		},
	]
