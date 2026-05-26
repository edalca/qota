# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, getdate, flt, today

from qota.billing.doctype.debt_ledger_entry.debt_ledger_entry import make_debt_ledger_entry


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
        """
        1. Zero out all existing outstanding DLEs for this contract.
        2. Create a DLE for the down payment (due immediately) if applicable.
        3. Create one DLE per installment with each installment's due date.
        """
        # 1. Zero out existing outstanding debt entries
        existing_dles = frappe.get_all(
            "Debt Ledger Entry",
            filters={
                "service_contract": self.service_contract,
                "status": ["in", ["Unpaid", "Partially Paid"]],
                "docstatus": ["!=", 2],
            },
            fields=["name", "amount", "reference_doctype", "reference_name"],
        )
        for dle in existing_dles:
            frappe.db.set_value(
                "Debt Ledger Entry",
                dle.name,
                {
                    "paid_amount": flt(dle.amount),
                    "outstanding_amount": 0,
                    "status": "Paid",
                },
                update_modified=False,
            )
            # Sync the referenced document (e.g. Monthly Bill) to Paid
            if dle.reference_doctype and dle.reference_name:
                if frappe.db.exists(dle.reference_doctype, dle.reference_name):
                    meta = frappe.get_meta(dle.reference_doctype)
                    if meta.has_field("status"):
                        frappe.db.set_value(
                            dle.reference_doctype,
                            dle.reference_name,
                            "status",
                            "Paid",
                            update_modified=False,
                        )

        # 2. Down payment DLE (due immediately)
        if flt(self.down_payment) > 0:
            make_debt_ledger_entry(
                contract_name=self.service_contract,
                entry_type="Refinancing Down Payment",
                amount=flt(self.down_payment),
                ref_dt=self.doctype,
                ref_dn=self.name,
                description=_("Refinancing Down Payment — {0}").format(self.name),
                reference_date=today(),
                skip_duplicate_check=True,
            )

        # 3. One DLE per installment
        for row in self.amortization_schedule:
            due = getdate(row.due_date)
            make_debt_ledger_entry(
                contract_name=self.service_contract,
                entry_type="Refinancing Installment",
                amount=flt(row.amount),
                ref_dt=self.doctype,
                ref_dn=self.name,
                description=_("Refinancing Installment — {0}").format(self.name),
                fiscal_month=due.month,
                fiscal_year=due.year,
                reference_date=str(row.due_date),
                skip_duplicate_check=True,
            )

        frappe.msgprint(_("Debt refinanced successfully. Down payment and installments are now active in the ledger."), indicator="green")


@frappe.whitelist()
def get_current_debt(contract_id):
    """Return the current outstanding balance for the given contract."""
    return get_contract_balance(contract_id)


def get_contract_balance(contract_id):
    """Query the ledger and return the total outstanding balance for a contract."""
    balance = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabDebt Ledger Entry`
        WHERE service_contract = %s
          AND outstanding_amount > 0.01
          AND docstatus != 2
    """, (contract_id,))
    return flt(balance[0][0]) if balance else 0.0
