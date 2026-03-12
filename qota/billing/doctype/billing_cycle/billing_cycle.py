# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, add_days, flt, today, formatdate


class BillingCycle(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.billing_cycle_issue.billing_cycle_issue import (
            BillingCycleIssue
        )

        amended_from: DF.Link | None
        billing_basis: DF.Literal["Flat Rate", "Metered", "All"]
        edit_posting_date: DF.Check
        end_date: DF.Date | None
        fiscal_month: DF.Literal["January",
                                 "February",
                                 "March",
                                 "April",
                                 "May",
                                 "June",
                                 "July",
                                 "August",
                                 "September",
                                 "October",
                                 "November",
                                 "December"]
        fiscal_year: DF.Link
        issues: DF.Table[BillingCycleIssue]
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
        self.validate_billing_window()

    def validate_billing_window(self) -> None:
        """
        Enforces fiscal and technical timing rules based on Billing Settings.
        - Prevents billing unfinished periods.
        - Restricts posting date backdating and future-dating.
        - Enforces reading window for Metered/All services.
        """
        settings = frappe.get_doc("Billing Settings")
        curr_today = getdate(today())
        end_dt = getdate(self.end_date)
        post_dt = getdate(self.posting_date)

        # 1. Period Integrity: Cannot bill a month that hasn't finished yet
        if end_dt >= curr_today:
            frappe.throw(_(
                "Cannot generate cycle. The coverage period must end "
                "before today. Period ends on: {0}"
            ).format(formatdate(self.end_date)))

        # 2. Posting Date: No future dates allowed
        if post_dt > curr_today:
            frappe.throw(_("Posting Date cannot be in the future."))

        # 3. Posting Date: Backdating limit enforcement
        if self.edit_posting_date:
            limit_days = int(settings.max_backdating_limit_days or 0)
            earliest_allowed = add_days(curr_today, -limit_days)

            if post_dt < earliest_allowed:
                frappe.throw(_(
                    "Posting Date is too far in the past. "
                    "Max allowed backdating is {0} days (Earliest: {1})."
                ).format(limit_days, formatdate(earliest_allowed)))

        if self.billing_basis in ["Metered", "All"]:
            window_days = int(settings.reading_window_days or 0)

            allowed_from = add_days(end_dt, window_days + 1)

            if curr_today < allowed_from:
                frappe.throw(_(
                    "Technical Window Error: You must wait until {0} to "
                    "process this cycle, allowing {1} days "
                    "for meter reading entry."
                ).format(formatdate(allowed_from), window_days))

    def validate_dates(self):
        """Ensures service dates are logically ordered"""
        if not self.start_date or not self.end_date:
            frappe.throw(_(
                "Please set the Start and End dates for "
                "the coverage period."))
        if getdate(self.end_date) < getdate(self.start_date):
            frappe.throw(_(
                "Service End Date cannot be earlier "
                "than Service Start Date"))

    def check_duplicate_cycle(self):
        """Prevents creating multiple cycles for the same month and year"""
        exists = frappe.db.exists("Billing Cycle", {
            "fiscal_year": self.fiscal_year,
            "fiscal_month": self.fiscal_month,
            "name": ["!=", self.name],
            "docstatus": ["!=", 2]
        })
        if exists:
            frappe.throw(_("A Billing Cycle already exists for {0} {1}")
                         .format(self.fiscal_month, self.fiscal_year))

    def validate_sequence(self):
        """Ensures there are no gaps between global billing cycles"""
        last_cycle = frappe.get_all(
            "Billing Cycle",
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
                frappe.throw(_(
                    "Billing Sequence Error: New cycle must start on {0} "
                    "to maintain continuity.").format(
                    frappe.format_date(expected_start)
                ))

    @frappe.whitelist()
    def reprocess_cycle_bills(self):
        """
        Surgically updates submitted bills for this specific cycle.
        """
        from qota.billing.utils import get_monthly_billing_breakdown

        # Usamos los valores del documento actual (self)
        fiscal_month = self.fiscal_month
        fiscal_year = self.fiscal_year

        # 1. Get all submitted bills for the period
        bills = frappe.get_all("Monthly Bill", filters={
            "fiscal_month": fiscal_month,
            "fiscal_year": fiscal_year,
            "docstatus": 1
        }, fields=["name", "service_contract", "start_date", "end_date"])

        if not bills:
            frappe.msgprint(_("No submitted bills found for {0}-{1}")
                            .format(fiscal_month, fiscal_year))
            return

        count = 0
        for b in bills:
            # 2. Identify and Reset Payment Links
            dle_name = frappe.db.get_value("Debt Ledger Entry",
                                           {"reference_name": b.name}, "name")

            if dle_name:
                frappe.db.sql("""
                    UPDATE `tabPayment Receipt Item`
                    SET debt_ledger_entry = NULL, balance = amount
                    WHERE debt_ledger_entry = %s
                """, dle_name)

            # 3. Recalculate
            breakdown = get_monthly_billing_breakdown(
                contract_name=b.service_contract,
                billing_month=fiscal_month,
                billing_year=fiscal_year,
                start_date=b.start_date,
                end_date=b.end_date
            )

            new_total = flt(breakdown.get("total_to_bill"))

            # 4. Update Items
            frappe.db.delete("Monthly Bill Item", {"parent": b.name})
            for item in breakdown.get("detailed_items", []):
                frappe.get_doc({
                    "doctype": "Monthly Bill Item",
                    "parent": b.name,
                    "parenttype": "Monthly Bill",
                    "parentfield": "items",
                    "description": item["description"],
                    "amount": item["amount"]
                }).db_insert()

            # 5. Update Bill Header
            frappe.db.set_value("Monthly Bill", b.name, {
                "grand_total": new_total,
                "billing_details_json": json.dumps(
                    breakdown.get("detailed_items", []))
            }, update_modified=True)

            # 6. Update Debt Ledger
            if dle_name:
                frappe.db.set_value("Debt Ledger Entry", dle_name, {
                    "amount": new_total,
                    "paid_amount": 0,
                    "outstanding_amount": new_total,
                    "status": "Unpaid"
                })

            # 7. Re-apply payments
            doc = frappe.get_doc("Monthly Bill", b.name)
            doc.apply_advance_payments()

            count += 1

        frappe.db.commit()
        return _(
            "Successfully reprocessed {0} bills for {1}-{2}"
            ).format(count, fiscal_month, fiscal_year)

    @frappe.whitelist()
    def reset_status(self):
        """
        Manually resets the status to 'Draft'
        if the background process gets stuck.
        This is necessary for error recovery when workers fail.
        """
        self.db_set("status", "Draft")
        self.db_set("docstatus", 0)
        self.db_set("total_generated", 0)
        self.db_set("total_contracts", 0)

        return True

    def on_submit(self):
        """Triggers the background process for real execution"""
        self.db_set("status", "Queue")
        frappe.enqueue(
            method=execute_billing_process,
            billing_cycle_name=self.name,
            queue='long',
            timeout=3600
        )
        frappe.msgprint(_(
            "Process queued for background execution."),
            alert=True)

    def on_cancel(self):
        """Rollback: Cancels all linked bills and updates status"""
        self.cancel_generated_bills()
        self.db_set("status", "Cancelled")

    def cancel_generated_bills(self):
        """
        Finds and cancels all submitted Monthly Bills linked to this cycle.
        This effectively rolls back the entire execution.
        """
        bills = frappe.get_all(
            "Monthly Bill",
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
                doc = frappe.get_doc("Monthly Bill", bill_name)
                doc.cancel()
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=_("Error cancelling bill {0} during cycle rollback")
                    .format(bill_name)
                )

    @frappe.whitelist()
    def get_billing_diagnostics(self):
        """
        Runs a simulation (Dry Run) to identify potential billing issues
        without creating real invoices or saving the document.
        """
        return self.run_billing_engine(is_dry_run=True)

    def run_billing_engine(self, is_dry_run=True):
        """
        Core billing engine.
        Populates 'issues' child table.
        Avoids self.save() on real runs to prevent docstatus errors.
        """
        self.set("issues", [])

        filters = {"status": "Active", "docstatus": 1}
        if self.billing_basis != "All":
            filters["billing_basis"] = self.billing_basis

        contracts = frappe.get_all(
            "Service Contract",
            filters=filters,
            fields=["name", "start_date", "billing_basis"],
            limit=0)
        results = {"total_gen": 0, "count": 0}

        for c in contracts:
            error_reason = None
            details = ""

            if getdate(c.start_date) > getdate(self.end_date):
                error_reason = "Future Start Date"
                details = f"Contract starts on {c.start_date}"

            elif frappe.db.exists("Monthly Bill", {
                "service_contract": c.name, "fiscal_year": self.fiscal_year,
                "fiscal_month": self.fiscal_month, "docstatus": ["!=", 2]
            }):
                error_reason = "Already Billed"
                details = "Bill already exists for this period."

            elif c.billing_basis == "Metered":
                if not frappe.db.exists(
                    "Meter Reading",
                    {
                        "service_contract": c.name,
                        "billing_cycle": self.name,
                        "docstatus": 1
                    }
                ):
                    error_reason = "Missing Reading"
                    details = "Required for metered service."

            if error_reason:
                self.append("issues",
                            {
                                "service_contract": c.name,
                                "reason": error_reason,
                                "details": details
                            })
                continue

            if not is_dry_run:
                try:
                    mb = frappe.new_doc("Monthly Bill")
                    mb.service_contract = c.name
                    mb.fiscal_year = self.fiscal_year
                    mb.fiscal_month = self.fiscal_month
                    mb.start_date = self.start_date
                    mb.end_date = self.end_date
                    mb.billing_cycle = self.name
                    mb.posting_date = self.posting_date
                    mb.insert(ignore_permissions=True)
                    mb.submit()
                    results["total_gen"] += flt(mb.grand_total)
                    results["count"] += 1
                except Exception as e:
                    self.append("issues", {
                        "service_contract": c.name,
                        "reason": "Execution Error",
                        "details": str(e)})

        if is_dry_run:
            self.save(ignore_permissions=True)

        return results


def execute_billing_process(billing_cycle_name):
    """Background task to process billing with proper state management."""
    try:
        cycle = frappe.get_doc("Billing Cycle", billing_cycle_name)
        out = cycle.run_billing_engine(is_dry_run=False)
        cycle.db_set("total_generated", out["total_gen"])
        cycle.db_set("total_contracts", out["count"])
        cycle.db_set("status", "Completed")

        frappe.publish_realtime("billing_cycle_finished", {
            "message": _("Finished: {0} bills created.").format(out["count"]),
            "name": cycle.name
        }, user=cycle.owner)

    except Exception:
        frappe.log_error(frappe.get_traceback(),
                         _("Billing Process Critical Failure"))

        frappe.db.set_value("Billing Cycle", billing_cycle_name, {
            "status": "Draft",
            "docstatus": 0
        })

        frappe.publish_realtime("billing_cycle_finished", {
            "message": _(
                "A critical error occurred. "
                "The cycle has been reset to Draft. Please check Error Logs."),
            "name": billing_cycle_name
        })
