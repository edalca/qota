# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, getdate, flt, today
from qota.billing.doctype.debt_ledger_entry.debt_ledger_entry import DebtLedgerEntry


class DebtRefinancing(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.amortization_schedule_item.amortization_schedule_item import AmortizationScheduleItem

        amended_from: DF.Link | None
        amortization_schedule: DF.Table[AmortizationScheduleItem]
        current_total_debt: DF.Currency
        down_payment: DF.Currency
        installments: DF.Int
        monthly_installment_amount: DF.Currency
        new_financed_debt: DF.Currency
        posting_date: DF.Date
        premises: DF.Link | None
        service_contract: DF.Link
        start_payment_date: DF.Date
        subscriber: DF.Data | None
    # end: auto-generated types

    def validate(self):
        self.fetch_debt_internal()
        self.calculate_schedule()

    def fetch_debt_internal(self):
        """Refresh the current debt balance from the ledger."""
        if self.service_contract:
            self.current_total_debt = get_contract_balance(self.service_contract)

    def calculate_schedule(self):
        """Build the amortization schedule based on the current debt and installment settings."""
        if self.current_total_debt <= 0:
            frappe.throw(_("This contract has no debt to refinance."))

        if self.down_payment >= self.current_total_debt:
            frappe.throw(_("Down payment covers the entire debt. Please use a Payment Receipt instead."))

        if self.installments < 1:
            frappe.throw(_("Installments must be at least 1."))

        self.new_financed_debt = flt(self.current_total_debt) - flt(self.down_payment)
        self.monthly_installment_amount = self.new_financed_debt / self.installments

        self.amortization_schedule = []
        start_date = getdate(self.start_payment_date)
        current_balance = self.new_financed_debt
        monthly_payment = self.monthly_installment_amount

        for i in range(self.installments):
            if i == self.installments - 1:
                amount = current_balance
            else:
                amount = monthly_payment

            self.append("amortization_schedule", {
                "due_date": add_months(start_date, i),
                "amount": amount,
                "status": "Pending"
            })
            current_balance -= amount

    def on_submit(self):
        """Cancel old debt, create unified refinanced debt, and record down payment."""
        DebtLedgerEntry.create_entry(
            contract=self.service_contract,
            entry_type="Adjustment",
            amount=-1 * self.current_total_debt,
            ref_dt="Debt Refinancing",
            ref_dn=self.name,
            posting_date=today()
        )

        DebtLedgerEntry.create_entry(
            contract=self.service_contract,
            entry_type="Adjustment",
            amount=self.current_total_debt,
            ref_dt="Debt Refinancing",
            ref_dn=self.name,
            posting_date=today()
        )

        if self.down_payment > 0:
            DebtLedgerEntry.create_entry(
                contract=self.service_contract,
                entry_type="Payment",
                amount=-1 * self.down_payment,
                ref_dt="Debt Refinancing",
                ref_dn=self.name,
                posting_date=today()
            )

        frappe.msgprint(_("Debt refinanced successfully."), indicator='green')


@frappe.whitelist()
def get_current_debt(contract_id):
    """Return the current outstanding balance for the given contract."""
    return get_contract_balance(contract_id)


def get_contract_balance(contract_id):
    """Query the ledger and return the total outstanding balance for a contract."""
    balance = frappe.db.sql("""
        SELECT SUM(amount) FROM `tabDebt Ledger Entry`
        WHERE service_contract = %s
    """, (contract_id,))
    return flt(balance[0][0]) if balance else 0.0
