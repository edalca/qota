# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import random

import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)

	return columns, data, None, chart


def get_columns():
	return [
		{"label": _("Subscriber"), "fieldname": "subscriber", "fieldtype": "Data", "width": 180},
		{"label": _("Service Contract"), "fieldname": "contract", "fieldtype": "Link", "options": "Service Contract", "width": 120},
		{"label": _("Block"), "fieldname": "block", "fieldtype": "Data", "width": 100},
		{"label": _("House Number"), "fieldname": "house_number", "fieldtype": "Data", "width": 100},
		{"label": _("Advance Amount"), "fieldname": "advance_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Advance Months"), "fieldname": "months_ahead", "fieldtype": "Int", "width": 110},
	]


def get_data(filters):
	"""Return Payment Receipt Items with no linked debt entry, representing advance payments."""
	receipt_filters = {"docstatus": 1}
	if filters.get("service_contract"):
		receipt_filters["service_contract"] = filters.get("service_contract")

	receipts = frappe.get_all(
		"Payment Receipt",
		filters=receipt_filters,
		fields=["name", "full_name", "service_contract"],
	)
	if not receipts:
		return []

	receipt_map = {r.name: r for r in receipts}
	contract_names = list({r.service_contract for r in receipts if r.service_contract})
	contracts = frappe.get_all(
		"Service Contract",
		filters={"name": ["in", contract_names]},
		fields=["name", "premises"],
	)
	contract_premises = {c.name: c.premises for c in contracts}

	premises_names = list({p for p in contract_premises.values() if p})
	premises = frappe.get_all(
		"Premises",
		filters={"name": ["in", premises_names]},
		fields=["name", "block", "house_number"],
	)
	premises_map = {p.name: p for p in premises}

	items = frappe.get_all(
		"Payment Receipt Item",
		filters={"parent": ["in", list(receipt_map)], "debt_ledger_entry": ["is", "not set"]},
		fields=["parent", "amount", "balance"],
	)

	grouped = {}
	for item in items:
		receipt = receipt_map.get(item.parent)
		if not receipt:
			continue

		premises_name = contract_premises.get(receipt.service_contract)
		p = premises_map.get(premises_name, frappe._dict())

		if filters.get("block") and p.get("block") != filters.get("block"):
			continue
		if filters.get("house_number") and p.get("house_number") != filters.get("house_number"):
			continue

		contract = receipt.service_contract
		if contract not in grouped:
			grouped[contract] = {
				"subscriber": receipt.full_name,
				"contract": contract,
				"block": p.get("block"),
				"house_number": p.get("house_number"),
				"advance_amount": 0,
				"months_ahead": 0,
			}
		grouped[contract]["advance_amount"] += item.amount
		if item.balance > 0:
			grouped[contract]["months_ahead"] += 1

	rows = sorted(grouped.values(), key=lambda r: (r.get("block") or "", r.get("house_number") or ""))
	return rows


def get_chart(data):
	"""Return a bar chart summarizing advance amounts grouped by block."""
	if not data:
		return None

	warm_colors = [
		"#E67E22",
		"#5DADE2",
		"#48C9B0",
		"#F4D03F",
		"#EB984E",
		"#AF7AC5",
		"#52BE80",
		"#EC7063",
		"#5499C7",
		"#A569BD",
	]

	block_summary = {}
	for row in data:
		block = row.get("block") or _("Unknown")
		block_summary[block] = block_summary.get(block, 0) + (row.get("advance_amount") or 0)

	labels = sorted(block_summary.keys())
	values = [block_summary[k] for k in labels]

	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("Advance Amount"), "values": values}],
		},
		"type": "bar",
		"colors": [random.choice(warm_colors)],
		"barOptions": {"spaceRatio": 0.5},
	}
