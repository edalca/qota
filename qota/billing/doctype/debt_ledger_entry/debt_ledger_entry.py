# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today, flt


class DebtLedgerEntry(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        amount: DF.Currency
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

    def validate(self):
        """
        Calculate the outstanding balance and update the status automatically.
        """
        self.amount = flt(self.amount)
        self.paid_amount = flt(self.paid_amount)
        
        # Balance Formula: Outstanding = Original - Paid
        self.outstanding_amount = self.amount - self.paid_amount
        
        # Status Management
        if self.outstanding_amount <= 0.01:
            self.status = "Paid"
        elif self.paid_amount > 0:
            self.status = "Partially Paid"
        else:
            self.status = "Unpaid"

    def on_cancel(self):
        """
        Prevent cancellation if there are active payment allocations.
        """
        allocations_exist = frappe.db.exists("Payment Allocation", {"debt_ledger_entry": self.name})
        if allocations_exist:
            frappe.throw(_("Cannot cancel this debt because it has allocated payments. Please cancel the associated payment receipts first."))