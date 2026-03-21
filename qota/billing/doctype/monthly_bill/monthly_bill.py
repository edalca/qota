# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import json
from typing import Optional
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from qota.billing.doctype.debt_ledger_entry.debt_ledger_entry import (
    make_debt_ledger_entry,
    clear_and_delete_debt
)


class MonthlyBill(Document):
    """
    Manages the monthly water service billing process.
    Coordinates with the Debt Ledger for financial impact and
    ensures billing continuity according to ERSAPS regulations.
    """

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.monthly_bill_item.monthly_bill_item import MonthlyBillItem

        amended_from: DF.Link | None
        billing_cycle: DF.Link | None
        billing_details_json: DF.SmallText | None
        edit_posting_date: DF.Check
        end_date: DF.Date | None
        fiscal_month: DF.Literal["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        fiscal_year: DF.Link
        full_name: DF.Data | None
        grand_total: DF.Currency
        items: DF.Table[MonthlyBillItem]
        posting_date: DF.Date
        premises: DF.Link | None
        service_contract: DF.Link
        start_date: DF.Date | None
        status: DF.Literal["Draft", "Unpaid", "Partially Paid", "Paid", "Cancelled"]
        subscriber: DF.Link | None
    # end: auto-generated types

    def validate(self) -> None:
        self.validate_dates()
        self.check_duplicate_fiscal_period()
        self.check_duplicate_period()
        self.validate_sequence()
        self.calculate_breakdown()

    def check_duplicate_fiscal_period(self) -> None:
        """
        Prevents duplicate bills for the same fiscal month/year.
        """
        duplicate = frappe.db.exists("Monthly Bill", {
            "service_contract": self.service_contract,
            "fiscal_year": self.fiscal_year,
            "fiscal_month": self.fiscal_month,
            "name": ["!=", self.name],
            "docstatus": ["!=", 2]
        })

        if duplicate:
            frappe.throw(_(
                "A Monthly Bill already exists for this contract "
                "in {0} {1} (Reference: {2})"
            ).format(self.fiscal_month, self.fiscal_year, duplicate))

    def validate_dates(self) -> None:
        """
        Ensures service dates are present and logically ordered.
        """
        if not self.start_date or not self.end_date:
            frappe.throw(_("Service Start Date and End Date are required."))

        if getdate(self.start_date) >= getdate(self.end_date):
            frappe.throw(_(
                "Service End Date must be after Service Start Date."
            ))

    def check_duplicate_period(self) -> None:
        """
        Prevents overlapping service periods (collision detection).
        """
        overlapping_bill = frappe.db.sql("""
            SELECT name FROM `tabMonthly Bill`
            WHERE service_contract = %s
              AND name != %s
              AND docstatus != 2
              AND (
                (%s BETWEEN start_date AND end_date) OR
                (%s BETWEEN start_date AND end_date) OR
                (start_date BETWEEN %s AND %s)
              )
            LIMIT 1
        """, (self.service_contract, self.name, self.start_date,
              self.end_date, self.start_date, self.end_date))

        if overlapping_bill:
            frappe.throw(_(
                "The selected date range overlaps with an "
                "existing Monthly Bill: {0}"
            ).format(overlapping_bill[0][0]))

    def validate_sequence(self, throw_error: bool = True) -> Optional[str]:
        """
        Ensures billing continuity.
        Validates that the previous month is billed ONLY if the contract was active.
        """
        from frappe.utils import getdate

        month_map = {
            "January": 1, "February": 2, "March": 3, "April": 4,
            "May": 5, "June": 6, "July": 7, "August": 8,
            "September": 9, "October": 10, "November": 11, "December": 12
        }
        rev_month_map = {v: k for k, v in month_map.items()}

        contract_data = frappe.db.get_value("Service Contract", self.service_contract,
            ["start_date", "reactivation_date"], as_dict=1)

        if not contract_data:
            return None

        start = getdate(contract_data.start_date)
        reactivation = getdate(contract_data.reactivation_date) if contract_data.reactivation_date else start

        effective_start = max(start, reactivation)
        effective_start_idx = (effective_start.year * 12) + effective_start.month

        oldest_open_year = frappe.db.get_value("Billing Year", {"is_closed": 0}, "year_name", order_by="year_name asc")
        if not oldest_open_year:
            return None

        open_year_idx = (int(oldest_open_year) * 12) + 1

        required_start_idx = max(effective_start_idx, open_year_idx)

        curr_year_val = frappe.db.get_value("Billing Year", self.fiscal_year, "year_name")
        if not curr_year_val:
            return None

        curr_idx = (int(curr_year_val) * 12) + month_map.get(self.fiscal_month)

        if curr_idx < required_start_idx:
            frappe.throw(_(
                "Invalid Period: Service was inactive or year is closed. "
                "First billable period is {0} {1}."
            ).format(_(rev_month_map[required_start_idx % 12 or 12]), (required_start_idx - 1) // 12))

        if curr_idx > required_start_idx:
            prev_idx = curr_idx - 1
            prev_month_num = prev_idx % 12 or 12
            prev_year_num = (prev_idx - 1) // 12

            exists = frappe.db.exists("Monthly Bill", {
                "service_contract": self.service_contract,
                "fiscal_month": rev_month_map[prev_month_num],
                "fiscal_year": frappe.db.get_value("Billing Year", {"year_name": str(prev_year_num)}, "name"),
                "docstatus": ["!=", 2]
            })

            if not exists:
                error_msg = _(
                    "Billing Continuity Error: Missing bill for {0} {1}. "
                    "You must bill sequentially since the last reactivation."
                ).format(_(rev_month_map[prev_month_num]), prev_year_num)

                if throw_error:
                    frappe.throw(error_msg)
                return error_msg

        return None

    def calculate_breakdown(self) -> None:
        """
        Executes the pricing engine to calculate m3 consumption and fees.
        """
        if not self.items and self.start_date and self.end_date:
            from qota.billing.utils import get_monthly_billing_breakdown

            breakdown = get_monthly_billing_breakdown(
                contract_name=self.service_contract,
                billing_month=self.fiscal_month,
                billing_year=self.fiscal_year,
                start_date=self.start_date,
                end_date=self.end_date
            )

            self.items = []
            for item in breakdown.get("detailed_items", []):
                self.append("items", {
                    "description": item["description"],
                    "amount": item["amount"]
                })

            self.grand_total = flt(breakdown.get("total_to_bill"))

    def on_submit(self) -> None:
        self.db_set("status", "Unpaid")
        self.create_debt_entry()
        self.prepare_audit_json()

    def on_cancel(self) -> None:
        clear_and_delete_debt(self.doctype, self.name)
        self.db_set("status", "Cancelled")

    def create_debt_entry(self) -> None:
        """
        Creates the debt in the Ledger.
        Note: The Ledger handles auto-payment of advances on its own on_submit.
        """
        year_val = frappe.db.get_value(
            "Billing Year", self.fiscal_year, "year_name"
        )
        month_map = {
            "January": 1,
            "February": 2,
            "March": 3,
            "April": 4,
            "May": 5,
            "June": 6,
            "July": 7,
            "August": 8,
            "September": 9,
            "October": 10,
            "November": 11,
            "December": 12
        }

        make_debt_ledger_entry(
            contract_name=self.service_contract,
            entry_type="Monthly Fee",
            amount=self.grand_total,
            ref_dt="Monthly Bill",
            ref_dn=self.name,
            description=_("Monthly Fee: {0} {1}").format(
                _(self.fiscal_month), year_val
            ),
            fiscal_month=month_map.get(self.fiscal_month),
            fiscal_year=int(year_val)
        )

    def prepare_audit_json(self) -> None:
        """
        Stores a snapshot of billing details for audit purposes.
        """
        details = [{"description": i.description, "amount": i.amount}
                   for i in self.items]
        self.db_set("billing_details_json", json.dumps(details))
