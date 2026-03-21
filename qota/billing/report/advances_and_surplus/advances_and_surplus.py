# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Return report column definitions."""
	return [
		{
			"label": _("Receipt"),
			"fieldname": "parent",
			"fieldtype": "Link",
			"options": "Payment Receipt",
			"width": 120,
		},
		{
			"label": _("Contract"),
			"fieldname": "service_contract",
			"fieldtype": "Link",
			"options": "Service Contract",
			"width": 120,
		},
		{"label": _("Subscriber"), "fieldname": "subscriber_name", "fieldtype": "Data", "width": 180},
		{"label": _("Payment Concept"), "fieldname": "payment_concept", "fieldtype": "Data", "width": 130},
		{"label": _("Period"), "fieldname": "billing_period", "fieldtype": "Data", "width": 100},
		{"label": _("Original Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Available Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	"""Return Payment Receipt Items with a remaining balance greater than zero."""
	receipt_filters = {"docstatus": 1}
	if filters.get("service_contract"):
		receipt_filters["service_contract"] = filters.get("service_contract")

	receipts = frappe.get_all(
		"Payment Receipt",
		filters=receipt_filters,
		fields=["name", "service_contract"],
	)
	if not receipts:
		return []

	receipt_map = {r.name: r for r in receipts}
	contract_names = list({r.service_contract for r in receipts if r.service_contract})
	contracts = frappe.get_all(
		"Service Contract",
		filters={"name": ["in", contract_names]},
		fields=["name", "full_name"],
	)
	contract_map = {c.name: c.full_name for c in contracts}

	items = frappe.get_all(
		"Payment Receipt Item",
		filters={"parent": ["in", list(receipt_map)], "balance": [">", 0]},
		fields=["parent", "payment_concept", "billing_period", "amount", "balance"],
		order_by="parent asc",
	)
	TRANSLATION = {
		"Monthly Fee": _("Monthly Fee"),
		"Connection Fee": _("Connection Fee"),
		"Late Fee": _("Late Fee"),
		"Reconnection Fee": _("Reconnection Fee"),
		"Other Fee": _("Other Fee"),
	}
	rows = []
	for item in items:
		receipt = receipt_map.get(item.parent)
		if not receipt:
			continue
		rows.append(
			{
				"parent": item.parent,
				"service_contract": receipt.service_contract,
				"subscriber_name": contract_map.get(receipt.service_contract, ""),
				"payment_concept": TRANSLATION.get(item.payment_concept, item.payment_concept),
				"billing_period": item.billing_period,
				"amount": flt(item.amount),
				"balance": flt(item.balance),
			}
		)
	return rows
