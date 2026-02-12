# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, add_days, flt, nowdate
from qota.billing.utils import get_monthly_billing_breakdown,make_debt_ledger_entry


class BillingCycle(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        billing_basis: DF.Literal["Flat Rate", "Metered", "All"]
        edit_posting_date: DF.Check
        end_date: DF.Date | None
        fiscal_month: DF.Literal["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        fiscal_year: DF.Link
        posting_date: DF.Date
        start_date: DF.Date | None
        status: DF.Literal["Draft", "Queue", "Completed", "Cancelled"]
        total_contracts: DF.Int
        total_generated: DF.Currency
    # end: auto-generated types

    def validate(self):
        """Restoring all your original validations"""
        self.validate_dates()
        self.check_duplicate_cycle()
        self.validate_sequence()

    def validate_dates(self):
        """Ensures service dates are logically ordered"""
        if not self.start_date or not self.end_date:
            frappe.throw(_("Please set the Start and End dates for the coverage period."))
        if getdate(self.end_date) < getdate(self.start_date):
            frappe.throw(_("Service End Date cannot be earlier than Service Start Date"))

    def check_duplicate_cycle(self):
        """Prevents creating multiple cycles for the same month and year"""
        exists = frappe.db.exists("Billing Cycle", {
            "fiscal_year": self.fiscal_year,
            "fiscal_month": self.fiscal_month,
            "name": ["!=", self.name],
            "docstatus": ["!=", 2]
        })
        if exists:
            frappe.throw(_("A Billing Cycle already exists for {0} {1}").format(
                self.fiscal_month, self.fiscal_year
            ))

    def validate_sequence(self):
        """Ensures there are no gaps between global billing cycles"""
        last_cycle = frappe.get_all("Billing Cycle",
            filters={"docstatus": 1, "name": ["!=", self.name]},
            fields=["end_date"],
            order_by="end_date desc",
            limit=1
        )
        if last_cycle:
            last_end = getdate(last_cycle[0].end_date)
            current_start = getdate(self.start_date)
            expected_start = add_days(last_end, 1)
            
            if current_start != expected_start:
                frappe.throw(_("Billing Sequence Error: New cycle must start on {0} to maintain continuity.").format(
                    frappe.format_date(expected_start)
                ))

    def on_submit(self):
        """Triggers the background process for real execution"""
        self.db_set("status", "Queue")
        frappe.enqueue(
            'qota.billing.doctype.billing_cycle.billing_cycle.execute_billing_process',
            billing_cycle_name=self.name,
            queue='long',
            timeout=3600
        )
        frappe.msgprint(_("Process queued for background execution."), alert=True)

    def on_cancel(self):
        """Rollback: Cancels all linked bills and updates status"""
        self.cancel_generated_bills()
        self.db_set("status", "Cancelled")
    
    def cancel_generated_bills(self):
        """
        Finds and cancels all submitted Monthly Bills linked to this cycle.
        This effectively rolls back the entire execution.
        """
        # Buscamos solo las facturas que están en estado 'Submitted' (docstatus 1)
        # Usamos pluck="name" para obtener una lista simple de IDs y ahorrar memoria
        bills = frappe.get_all("Monthly Bill", 
            filters={
                "billing_cycle": self.name, 
                "docstatus": 1
            }, 
            pluck="name"
        )

        if not bills:
            return

        for bill_name in bills:
            try:
                # Cargamos cada documento y lo cancelamos
                doc = frappe.get_doc("Monthly Bill", bill_name)
                doc.cancel()
            except Exception:
                # Si una falla (por ejemplo, porque ya está pagada), 
                # dejamos registro pero seguimos con las demás.
                frappe.log_error(
                    message=frappe.get_traceback(), 
                    title=_("Error cancelling bill {0} during cycle rollback").format(bill_name)
                )

    @frappe.whitelist()
    def get_billing_diagnostics(self):
        """Entry point for the UI to show issues without saving anything"""
        return self.run_billing_engine(is_dry_run=True)
    
    def run_billing_engine(self, is_dry_run=True):
        """
        The core engine. 
        If is_dry_run=True: Returns grouped issues.
        If is_dry_run=False: Generates and submits bills, returns totals.
        """
        filters = {"status": "Active", "docstatus": 1}
        if self.billing_basis != "All":
            filters["billing_basis"] = self.billing_basis

        # Fetch all contracts (limit=0 for the 758+ cases)
        contracts = frappe.get_all("Service Contract", filters=filters, fields=["name", "start_date"], limit=0)
        
        grouped_issues = {}
        results = {"total_gen": 0, "count": 0}

        for c in contracts:
            # 1. Basic Date Check
            if getdate(c.start_date) > getdate(self.end_date):
                frappe.log_error(f"Contract {c.name} skipped: Start date {c.start_date} is after cycle end date {self.end_date}.", "Billing Date Mismatch")
                continue

            # 2. Duplicate Check (Only for real runs)
            if not is_dry_run:
                if frappe.db.exists("Monthly Bill", {
                    "service_contract": c.name, "fiscal_year": self.fiscal_year,
                    "fiscal_month": self.fiscal_month, "docstatus": ["!=", 2]
                }):
                    frappe.log_error(f"Contract {c.name} skipped: Bill already exists for this cycle.", "Billing Duplicate")
                    continue

            # 3. Object Initialization
            mb = frappe.new_doc("Monthly Bill")
            mb.service_contract = c.name
            mb.fiscal_year = self.fiscal_year
            mb.fiscal_month = self.fiscal_month
            mb.start_date = self.start_date
            mb.end_date = self.end_date
            mb.billing_cycle = self.name
            mb.posting_date = self.posting_date

            # 4. Sequence Validation
            reason = mb.validate_sequence(throw_error=False)

            if reason:
                if is_dry_run:
                    if reason not in grouped_issues: grouped_issues[reason] = []
                    grouped_issues[reason].append(c.name)
                else:
                    # Log continuity errors during real run
                    frappe.log_error(f"Contract {c.name} skipped: {reason}", "Billing Continuity Gap")
                continue

            # 5. Real Execution
            if not is_dry_run:
                try:
                    mb.insert(ignore_permissions=True)
                    mb.submit()
                    results["total_gen"] += flt(mb.grand_total)
                    results["count"] += 1
                except Exception:
                    frappe.log_error(frappe.get_traceback(), _("Error processing {0}").format(c.name))

        if is_dry_run:
            return [{"reason": k, "contracts": v} for k, v in grouped_issues.items()]
        
        return results

# Worker Wrapper
def execute_billing_process(billing_cycle_name):
    cycle = frappe.get_doc("Billing Cycle", billing_cycle_name)
    
    # Run the engine in 'Real Mode'
    out = cycle.run_billing_engine(is_dry_run=False)

    # Sync and notify
    cycle.db_set("total_generated", out["total_gen"])
    cycle.db_set("total_contracts", out["count"])
    cycle.db_set("status", "Completed")
    
    frappe.publish_realtime("billing_cycle_finished", {
        "message": _("Finished: {0} bills created.").format(out["count"]), 
        "name": cycle.name
    }, user=cycle.owner)