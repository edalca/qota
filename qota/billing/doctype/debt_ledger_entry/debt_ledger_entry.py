# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate, today


class DebtLedgerEntry(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amended_from: DF.Link | None
		amount: DF.Currency
		billing_period: DF.Data | None
		description: DF.SmallText | None
		due_date: DF.Date | None
		entry_type: DF.Literal["Monthly Fee", "Connection Fee", "Late Fee", "Reconnection Fee", "Other Fee"]
		outstanding_amount: DF.Currency
		paid_amount: DF.Currency
		reference_doctype: DF.Link | None
		reference_name: DF.DynamicLink | None
		service_contract: DF.Link
		status: DF.Literal["Unpaid", "Partially Paid", "Paid"]
	# end: auto-generated types

	def validate(self) -> None:
		self.amount = flt(self.amount)
		self.paid_amount = flt(self.paid_amount)

		self.outstanding_amount = self.amount - self.paid_amount

		if self.outstanding_amount <= 0.01:
			self.status = "Paid"
		elif self.paid_amount > 0:
			self.status = "Partially Paid"
		else:
			self.status = "Unpaid"

	def after_insert(self) -> None:
		self.apply_advance_payments()

	def on_update(self) -> None:
		self.sync_reference_document_status()

	def apply_advance_payments(self) -> None:
		"""
		Checks for available balances in Payment Receipts for the same period.

		If money is found, it is applied to this debt, updating both
		the Ledger Entry and the source Receipt Item.

		Args:
		    None
		Returns:
		    None
		"""
		if not self.billing_period or not self.service_contract:
			return

		advance = frappe.db.sql(
			"""
            SELECT item.name, item.balance, item.amount
            FROM `tabPayment Receipt Item` item
            INNER JOIN `tabPayment Receipt` parent ON parent.name = item.parent
            WHERE parent.service_contract = %s
              AND item.billing_period = %s
              AND parent.docstatus = 1
              AND item.balance > 0
            LIMIT 1
        """,
			(self.service_contract, self.billing_period),
			as_dict=True,
		)

		if advance:
			adv_item = advance[0]
			available_money: float = flt(adv_item.balance)
			needed_money: float = flt(self.outstanding_amount)

			amount_to_apply: float = min(available_money, needed_money)

			self.paid_amount = flt(self.paid_amount) + amount_to_apply
			self.outstanding_amount = flt(self.amount) - self.paid_amount

			if self.outstanding_amount <= 0.01:
				self.status = "Paid"
			elif self.paid_amount > 0:
				self.status = "Partially Paid"

			self.db_update()
			self.sync_reference_document_status()
			new_balance: float = available_money - amount_to_apply

			frappe.db.set_value(
				"Payment Receipt Item",
				adv_item.name,
				{"balance": new_balance, "debt_ledger_entry": self.name},
			)

	def sync_reference_document_status(self) -> None:
		"""
		Directly pushes the current status to the source document.
		"""
		if not self.reference_doctype or not self.reference_name:
			return

		if frappe.db.get_value("DocType", self.reference_doctype, "name"):
			meta = frappe.get_meta(self.reference_doctype)
			if meta.has_field("status"):
				frappe.db.set_value(
					self.reference_doctype, self.reference_name, "status", self.status, update_modified=True
				)

	def on_cancel(self):
		"""
		Prevent cancellation if there are active payment allocations.
		"""
		frappe.throw(
			_("Debt Ledger Entries cannot be cancelled manually. This creates accounting inconsistencies.")
		)


def clear_and_delete_debt(reference_doctype: str, reference_name: str) -> None:
	"""
	Centralized logic to validate payments and delete a debt entry.
	"""
	debt_id: str | None = frappe.db.get_value(
		"Debt Ledger Entry",
		{"reference_doctype": reference_doctype, "reference_name": reference_name},
		"name",
	)

	if not debt_id:
		return

	debt = frappe.get_doc("Debt Ledger Entry", debt_id)

	if flt(debt.paid_amount) > 0:
		formatted_paid = frappe.format_value(debt.paid_amount, {"fieldtype": "Currency"})
		frappe.throw(
			_(
				"Cannot cancel because the associated debt has recorded "
				"payments ({0}). Please cancel the related Payment "
				"Receipts first."
			).format(formatted_paid)
		)

	frappe.db.sql(
		"""
        UPDATE `tabPayment Receipt Item`
        SET debt_ledger_entry = NULL
        WHERE debt_ledger_entry = %s
    """,
		debt_id,
	)

	frappe.delete_doc("Debt Ledger Entry", debt_id, force=1)


def make_debt_ledger_entry(
	contract_name: str,
	entry_type: str,
	amount: float,
	ref_dt: str | None = None,
	ref_dn: str | None = None,
	description: str | None = None,
	fiscal_month: int | None = None,
	fiscal_year: int | None = None,
) -> "DebtLedgerEntry":
	"""
	Creates and submits a Debt Ledger Entry with specialized period logic.
	"""
	if flt(amount) <= 0:
		frappe.throw(_("Amount must be greater than zero to create a Debt Ledger Entry."))

	if fiscal_month and fiscal_year:
		m: int = int(fiscal_month)
		y: int = int(fiscal_year)
	else:
		current_date = getdate(today())
		m: int = current_date.month
		y: int = current_date.year

	billing_period: str = f"{m:02d}-{y}"
	settings = frappe.get_doc("Billing Settings")

	days_to_add: int = 0
	if entry_type == "Connection Fee":
		days_to_add = int(settings.connection_debt_deadline_days or 30)
	elif entry_type == "Monthly Fee":
		days_to_add = int(settings.days_until_due or 15)
	else:
		days_to_add = int(settings.grace_period or 0)

	calculated_due_date: str = add_days(today(), days_to_add)

	debt = frappe.get_doc(
		{
			"doctype": "Debt Ledger Entry",
			"service_contract": contract_name,
			"entry_type": entry_type,
			"amount": flt(amount),
			"due_date": calculated_due_date,
			"paid_amount": 0,
			"outstanding_amount": flt(amount),
			"reference_doctype": ref_dt,
			"reference_name": ref_dn,
			"description": description,
			"status": "Unpaid",
			"billing_period": billing_period,
		}
	)

	debt.insert(ignore_permissions=True)
	return debt
