# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today, getdate, add_months, add_days, formatdate
from qota.billing.utils import make_debt_ledger_entry


class BillingCycle(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        billing_basis: DF.Literal["Flat Rate", "Metered", "All"]
        fiscal_month: DF.Literal["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        fiscal_year: DF.Link
        posting_date: DF.Date
        service_end_date: DF.Date
        service_start_date: DF.Date
        status: DF.Literal["Draft", "Completed", "Cancelled"]
    # end: auto-generated types

    def validate(self):
        # Auto-calculate dates based on settings
        if not self.service_start_date or not self.service_end_date:
            from qota.billing.utils import get_monthly_billing_breakdown
            self.calculate_service_period()

    @frappe.whitelist()
    def calculate_service_period(self):
        settings = frappe.get_doc("Billing Settings")
        start_day = int(settings.cycle_start_day or 1)
        try:
            date_str = f"{self.fiscal_year}-{self.fiscal_month}-01"
            ref_date = getdate(frappe.utils.data.get_datetime_str(date_str))
        except:
            ref_date = getdate(today())

        if start_day == 1:
            start, end = ref_date.replace(day=1), add_days(add_months(ref_date.replace(day=1), 1), -1)
        else:
            start = add_months(ref_date.replace(day=start_day), -1)
            end = add_days(ref_date.replace(day=start_day), -1)
        
        self.service_start_date, self.service_end_date = start, end
        return {"service_start_date": start, "service_end_date": end}

    def on_submit(self):
        """
        Calculates and generates entries, then saves the summary.
        """
        self.generate_billing_entries()

    def generate_billing_entries(self):
        # 1. Logic for Billing Basis filtering
        filters = {"status": "Active", "docstatus": 1}
        if self.billing_basis != "All":
            filters["billing_basis"] = self.billing_basis

        active_contracts = frappe.get_all("Service Contract", filters=filters, fields=["name"])

        if not active_contracts:
            frappe.throw(_("No active contracts found for the selected criteria."))

        total_amt = 0.0
        total_count = 0
        date_range = f"{formatdate(self.service_start_date)} - {formatdate(self.service_end_date)}"

        for contract in active_contracts:
            entry_name = make_debt_ledger_entry(
                contract_name=contract.name,
                entry_type="Monthly Fee",
                year=self.fiscal_year,
                month=self.fiscal_month,
                posting_date=self.posting_date,
                ref_dt=self.doctype,
                ref_dn=self.name,
                description=f"{self.billing_basis} Billing: {date_range}"
            )
            
            if entry_name:
                # Accumulate the total generated for the Summary Section
                amt = frappe.db.get_value("Debt Ledger Entry", entry_name, "amount")
                total_amt += flt(amt)
                total_count += 1

        # 2. Update SUMMARY fields (Important!)
        self.db_set("total_generated", total_amt)
        self.db_set("total_contracts", total_count)
        self.db_set("status", "Completed")

        frappe.msgprint(_("Billing Cycle Completed. {0} records generated for a total of {1}").format(
            total_count, frappe.format(total_amt, "Currency")), indicator="green")

    def on_cancel(self):
        # Rollback logic
        frappe.db.delete("Debt Ledger Entry", {"reference_doctype": self.doctype, "reference_name": self.name})
        self.db_set("total_generated", 0)
        self.db_set("total_contracts", 0)
        self.db_set("status", "Cancelled")