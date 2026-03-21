# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	if not filters.get("service_contract"):
		return [], []

	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": _("Doctype"), "fieldname": "reference_doctype", "fieldtype": "Data", "width": 150},
		{
			"label": _("Reference"),
			"fieldname": "reference",
			"fieldtype": "Dynamic Link",
			"options": "reference_doctype",
			"width": 140,
		},
		{"label": _("Billing Period"), "fieldname": "billing_period", "fieldtype": "Data", "width": 120},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 250},
		{"label": _("Debit (Charges)"), "fieldname": "debit", "fieldtype": "Currency", "width": 120},
		{"label": _("Credit (Payments)"), "fieldname": "credit", "fieldtype": "Currency", "width": 120},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	"""Return ledger rows sorted by date with a running balance column."""
	contract = filters.get("service_contract")

	rows = _get_debt_rows(contract) + _get_payment_rows(contract)
	rows.sort(key=lambda r: r["posting_date"])

	running_balance = 0
	for row in rows:
		running_balance += flt(row["debit"]) - flt(row["credit"])
		row["balance"] = running_balance

	return rows


def _get_debt_rows(contract):
	"""Return charge rows from Debt Ledger Entry for the given contract."""
	entries = frappe.get_all(
		"Debt Ledger Entry",
		filters={"service_contract": contract, "docstatus": ["!=", 2]},
		fields=["creation", "name", "description", "billing_period", "amount"],
	)
	return [
		{
			"posting_date": e.creation,
			"reference_doctype": "Debt Ledger Entry",
			"reference": e.name,
			"description": e.description,
			"billing_period": e.billing_period,
			"debit": e.amount,
			"credit": 0,
		}
		for e in entries
	]


def _get_payment_rows(contract):
	"""Return credit rows from Payment Receipt Items for the given contract."""
	receipts = frappe.get_all(
		"Payment Receipt",
		filters={"service_contract": contract, "docstatus": 1},
		fields=["name", "payment_date"],
	)
	if not receipts:
		return []

	receipt_date = {r.name: r.payment_date for r in receipts}
	items = frappe.get_all(
		"Payment Receipt Item",
		filters={"parent": ["in", list(receipt_date)]},
		fields=["parent", "description", "billing_period", "amount"],
	)
	return [
		{
			"posting_date": receipt_date[item.parent],
			"reference_doctype": "Payment Receipt",
			"reference": item.parent,
			"description": item.description,
			"billing_period": item.billing_period,
			"debit": 0,
			"credit": item.amount,
		}
		for item in items
	]
