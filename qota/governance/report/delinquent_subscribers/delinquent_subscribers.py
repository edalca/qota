# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	summary = get_report_summary(data)
	return columns, data, None, None, summary


def get_columns():
	return [
		{
			"label": _("Contract"),
			"fieldname": "contract",
			"fieldtype": "Link",
			"options": "Service Contract",
			"width": 130,
		},
		{
			"label": _("Subscriber Name"),
			"fieldname": "subscriber_name",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Block"),
			"fieldname": "block",
			"fieldtype": "Int",
			"width": 90,
		},
		{
			"label": _("House No."),
			"fieldname": "house_number",
			"fieldtype": "Int",
			"width": 90,
		},
		{
			"label": _("Contract Status"),
			"fieldname": "contract_status",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Overdue Periods"),
			"fieldname": "overdue_periods",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": _("Total Outstanding"),
			"fieldname": "total_outstanding",
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"label": _("Advance Balance"),
			"fieldname": "advance_balance",
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"label": _("Net Outstanding"),
			"fieldname": "net_outstanding",
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"label": _("Oldest Unpaid Period"),
			"fieldname": "oldest_period",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Suspension"),
			"fieldname": "suspension_status",
			"fieldtype": "Data",
			"width": 120,
		},
	]


def _to_int(value):
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def get_data(filters):
	filters = filters or {}

	settings = frappe.get_single("Billing Settings")
	suspension_threshold = int(settings.suspension_months_limit or 1)
	min_debt = flt(settings.min_debt_for_suspension or 0)
	grace_days = int(settings.grace_period or 0)
	as_of = getdate(today())

	contract_status_filter = filters.get("contract_status")
	min_periods = int(filters.get("min_periods") or suspension_threshold)
	premises_filter = filters.get("premises")

	# Only Monthly Fee entries map 1-to-1 with Monthly Bills — exclude only cancelled
	entries = frappe.get_all(
		"Debt Ledger Entry",
		filters={
			"entry_type": "Monthly Fee",
			"outstanding_amount": [">", 0],
			"docstatus": ["!=", 2],
		},
		fields=["service_contract", "outstanding_amount", "due_date", "billing_period"],
	)
	if not entries:
		return []

	contract_names = list({e.service_contract for e in entries})

	status_conditions = ["Active", "Suspended"]
	if contract_status_filter:
		status_conditions = [contract_status_filter]

	contracts = frappe.get_all(
		"Service Contract",
		filters={"name": ["in", contract_names], "status": ["in", status_conditions]},
		fields=["name", "subscriber", "full_name", "premises", "status"],
	)
	if not contracts:
		return []

	contract_map = {c.name: c for c in contracts}
	active_contract_names = set(contract_map.keys())

	premises_names = list({c.premises for c in contracts if c.premises})
	premises_map = {}
	if premises_names:
		premises_list = frappe.get_all(
			"Premises",
			filters={"name": ["in", premises_names]},
			fields=["name", "block", "house_number"],
		)
		premises_map = {p.name: p for p in premises_list}

	# Advance balance: sum of Payment Receipt Items with remaining balance > 0
	advance_map = _get_advance_balance_map(list(active_contract_names))

	suspensions = frappe.get_all(
		"Service Suspension",
		filters={
			"service_contract": ["in", list(active_contract_names)],
			"status": ["in", ["Scheduled", "Executed"]],
			"docstatus": ["!=", 2],
		},
		fields=["service_contract", "status"],
	)
	suspension_map = {s.service_contract: s.status for s in suspensions}

	grouped = {}
	for entry in entries:
		cid = entry.service_contract
		if cid not in active_contract_names:
			continue

		contract = contract_map[cid]
		if premises_filter and contract.premises != premises_filter:
			continue

		if cid not in grouped:
			p = premises_map.get(contract.premises, frappe._dict())
			grouped[cid] = {
				"contract": cid,
				"subscriber_name": contract.full_name,
				"block": _to_int(p.get("block")),
				"house_number": _to_int(p.get("house_number")),
				"contract_status": contract.status,
				"overdue_periods": 0,
				"total_outstanding": 0.0,
				"advance_balance": flt(advance_map.get(cid, 0)),
				"net_outstanding": 0.0,
				"oldest_period": "",
				"due_entries": [],
				"suspension_status": suspension_map.get(cid, ""),
			}

		if not _is_past_due(entry.due_date, as_of, grace_days):
			continue

		grouped[cid]["due_entries"].append(
			{
				"due_date": getdate(entry.due_date),
				"billing_period": entry.billing_period or "",
				"outstanding": flt(entry.outstanding_amount),
			}
		)
		grouped[cid]["total_outstanding"] += flt(entry.outstanding_amount)

	for row in grouped.values():
		_apply_advance_to_overdue_months(row)

	rows = [
		r
		for r in grouped.values()
		if r["overdue_periods"] >= min_periods and r["net_outstanding"] > 0.01 and r["net_outstanding"] >= min_debt
	]

	rows.sort(key=lambda r: (r["block"] or 0, r["house_number"] or 0))
	return rows


def _is_past_due(due_date, as_of, grace_days):
	"""A monthly fee is overdue only after its due date plus the grace period."""
	if not due_date:
		return False
	return as_of > getdate(add_days(due_date, grace_days))


def _apply_advance_to_overdue_months(row):
	"""Cover the oldest overdue months with the monthly-fee advance.

	A prepaid year leaves open charges for the months already billed and a
	credit for the months not billed yet. Those charges are not arrears while
	the credit covers them. The net balance stays negative when the subscriber
	has paid more than the overdue fees.
	"""
	credit = flt(row["advance_balance"])
	uncovered = 0
	oldest_period = ""
	for entry in sorted(row.pop("due_entries"), key=lambda item: (item["due_date"], item["billing_period"])):
		outstanding = flt(entry["outstanding"])
		if credit >= outstanding - 0.01:
			credit -= outstanding
			continue
		credit = 0
		uncovered += 1
		if not oldest_period:
			oldest_period = entry["billing_period"]

	row["overdue_periods"] = uncovered
	row["oldest_period"] = oldest_period
	row["net_outstanding"] = flt(row["total_outstanding"]) - flt(row["advance_balance"])


def _get_advance_balance_map(contract_names):
	"""Return {service_contract: total_advance_balance} for the given contracts."""
	if not contract_names:
		return {}

	receipts = frappe.get_all(
		"Payment Receipt",
		filters={"service_contract": ["in", contract_names], "docstatus": 1},
		fields=["name", "service_contract"],
	)
	if not receipts:
		return {}

	receipt_map = {r.name: r.service_contract for r in receipts}

	# Only Monthly Fee advance balance is comparable against Monthly Fee outstanding
	items = frappe.get_all(
		"Payment Receipt Item",
		filters={"parent": ["in", list(receipt_map)], "payment_concept": "Monthly Fee", "balance": [">", 0]},
		fields=["parent", "balance"],
	)

	advance_map = {}
	for item in items:
		cid = receipt_map.get(item.parent)
		if cid:
			advance_map[cid] = advance_map.get(cid, 0) + flt(item.balance)

	return advance_map


def get_report_summary(data):
	if not data:
		return []

	total_subscribers = len(data)
	total_outstanding = sum(r["total_outstanding"] for r in data)
	total_net = sum(r["net_outstanding"] for r in data)
	total_advance = sum(r["advance_balance"] for r in data)

	return [
		{
			"value": total_subscribers,
			"label": _("Delinquent Subscribers"),
			"datatype": "Int",
			"indicator": "Red",
		},
		{
			"value": total_outstanding,
			"label": _("Gross Outstanding"),
			"datatype": "Currency",
			"indicator": "Orange",
		},
		{
			"value": total_advance,
			"label": _("Total Advance Balance"),
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"value": total_net,
			"label": _("Net Outstanding"),
			"datatype": "Currency",
			"indicator": "Red",
		},
	]
