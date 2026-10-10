# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	if not filters.get("service_contract"):
		return [], []

	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": _("Doctype"), "fieldname": "document_type", "fieldtype": "Data", "width": 180},
		{
			"label": _("Reference"),
			"fieldname": "reference",
			"fieldtype": "Dynamic Link",
			"options": "reference_doctype",
			"width": 140,
		},
		{"fieldname": "reference_doctype", "fieldtype": "Data", "hidden": 1},
		{"label": _("Billing Period"), "fieldname": "billing_period", "fieldtype": "Data", "width": 120},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 250},
		{"label": _("Debit (Charges)"), "fieldname": "debit", "fieldtype": "Currency", "width": 120},
		{"label": _("Credit (Payments)"), "fieldname": "credit", "fieldtype": "Currency", "width": 120},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	"""Return ledger rows sorted by date with a running balance column."""
	contract = filters.get("service_contract")

	rows = _get_debt_rows(contract) + _get_payment_rows(contract) + _get_refinancing_rows(contract)
	rows.sort(key=lambda r: r["posting_date"])

	running_balance = 0
	for row in rows:
		running_balance += flt(row["debit"]) - flt(row["credit"])
		row["balance"] = running_balance

	return _apply_date_filter(rows, filters)


def _apply_date_filter(rows, filters):
	"""Keep the running balance and show only the requested dates.

	Rows before From Date collapse into an opening balance. Rows after To
	Date are left out. Without either filter the full statement is returned.
	"""
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	if not from_date and not to_date:
		return rows

	visible = []
	opening = 0
	for row in rows:
		row_date = getdate(row["posting_date"])
		if from_date and row_date < getdate(from_date):
			opening = row["balance"]
			continue
		if to_date and row_date > getdate(to_date):
			continue
		visible.append(row)

	if from_date:
		visible.insert(
			0,
			{
				"posting_date": getdate(from_date),
				"reference_doctype": "Debt Ledger Entry",
				"document_type": _("Opening Balance"),
				"reference": "",
				"description": _("Opening Balance"),
				"billing_period": None,
				"debit": 0,
				"credit": 0,
				"balance": opening,
			},
		)
	return visible


def _get_debt_rows(contract):
	"""Return charge rows from Debt Ledger Entry for the given contract."""
	entries = frappe.get_all(
		"Debt Ledger Entry",
		filters={"service_contract": contract, "docstatus": ["!=", 2]},
		fields=["creation", "name", "description", "billing_period", "amount"],
	)
	return [
		{
			"posting_date": entry.creation,
			"reference_doctype": "Debt Ledger Entry",
			"document_type": _("Debt Ledger Entry"),
			"reference": entry.name,
			"description": entry.description,
			"billing_period": entry.billing_period,
			"debit": entry.amount,
			"credit": 0,
		}
		for entry in entries
	]


def _get_refinancing_rows(contract):
	"""Return one credit row per refinancing: the document is the counterpart.

	The old charges stay on the statement. The refinancing itself, for example
	REF-2600003, credits the outstanding balance it cancelled. The new
	installments remain as their own charges.
	"""
	refinancings = frappe.get_all(
		"Debt Refinancing",
		filters={"service_contract": contract, "docstatus": 1},
		fields=["name", "creation", "posting_date", "current_total_debt"],
	)
	rows = []
	for refinancing in refinancings:
		amount = flt(refinancing.current_total_debt)
		if amount <= 0.01:
			continue
		transaction_date = getdate(refinancing.posting_date)
		rows.append(
			{
				"posting_date": refinancing.creation,
				"reference_doctype": "Debt Refinancing",
				"document_type": _("Debt Refinancing"),
				"reference": refinancing.name,
				"description": _("Previous debt cancelled by refinancing"),
				"billing_period": f"{transaction_date.month:02d}-{transaction_date.year}",
				"debit": 0,
				"credit": amount,
			}
		)
	return rows


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
			"document_type": _("Payment Receipt"),
			"reference": item.parent,
			"description": item.description,
			"billing_period": item.billing_period,
			"debit": 0,
			"credit": item.amount,
		}
		for item in items
	]
