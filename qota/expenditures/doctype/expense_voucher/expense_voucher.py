# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money


class ExpenseVoucher(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        amount: DF.Currency
        expense_category: DF.Link
        mode_of_payment: DF.Literal["Cash", "Bank Transfer", "Check", "Other"]
        payee: DF.Data
        posting_date: DF.Datetime
        reference_no: DF.Data | None
        remarks: DF.SmallText | None
        status: DF.Literal["Draft", "Paid", "Cancelled"]
    # end: auto-generated types

    def validate(self) -> None:
        self.validate_amount()
        self.sync_status_with_docstatus()

    def validate_amount(self) -> None:
        """
        Prevents submission of zero or negative expenditure values.
        """
        if flt(self.amount) <= 0:
            frappe.throw(
                _("The expense amount {0} must be greater than zero.")
                .format(fmt_money(self.amount))
            )

    def sync_status_with_docstatus(self) -> None:
        """
        Synchronizes the readable 'Status' field with Frappe's
        internal docstatus.
        """
        if self.docstatus == 0:
            self.status = "Draft"
        elif self.docstatus == 1:
            self.status = "Paid"
        elif self.docstatus == 2:
            self.status = "Cancelled"

    def on_submit(self) -> None:
        self.db_set("status", "Paid")

    def on_cancel(self) -> None:
        self.db_set("status", "Cancelled")
