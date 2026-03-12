# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    flt,
    getdate,
    today,
    formatdate,
    fmt_money,
    add_days
)
from qota.governance.doctype.service_contract.service_contract import (
    update_contract_property
)


class ServiceSuspension(Document):
    """
    Manages service suspension.
    Updates contract status and records final readings only
    for metered services.
    """
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        billing_basis: DF.Literal["", "Flat Rate", "Metered"]
        edit_posting_date: DF.Check
        effective_date: DF.Date | None
        executed_date: DF.Date | None
        final_reading: DF.Float
        full_name: DF.Data | None
        posting_date: DF.Datetime
        premises: DF.Link | None
        reason: DF.Literal["Arrears", "Subscriber Request", "Fraud / Bypass", "Sanction", "Maintenance", "Other"]
        remarks: DF.SmallText | None
        service_contract: DF.Link
        status: DF.Literal["Draft", "Scheduled", "Executed"]
        subscriber: DF.Link | None
        suspension_type: DF.Literal["Administrative", "By Request"]
    # end: auto-generated types

    def validate(self) -> None:
        """Main validation entry point."""
        self.validate_contract_eligibility()
        self.validate_posting_date()
        self.validate_suspension_rules()

        if self.status == "Executed":
            self.validate_technical_execution()

    def validate_contract_eligibility(self) -> None:
        """Checks if the contract is Active and ready for suspension."""
        status = frappe.db.get_value("Service Contract", self.service_contract,
                                     "status")
        if status == "Suspended" and self.is_new():
            frappe.throw(_("Contract {0} is already suspended.")
                         .format(self.service_contract))

        if status in ["Closed", "Cancelled"]:
            frappe.throw(_("Cannot suspend a contract in '{0}' status.")
                         .format(status))

        duplicate_order = frappe.db.exists("Service Suspension", {
            "service_contract": self.service_contract,
            "status": ["in", ["Draft", "Scheduled"]],
            "name": ["!=", self.name],
            "docstatus": ["<", 2]
        })

        if duplicate_order:
            frappe.throw(_(
                "There is already a pending suspension order ({0}) "
                "for this contract.")
                .format(duplicate_order))

    def validate_posting_date(self) -> None:
        """Ensures the suspension date is not before the contract start."""
        start_date = frappe.db.get_value("Service Contract",
                                         self.service_contract, "start_date")
        if getdate(self.posting_date) < getdate(start_date):
            frappe.throw(_(
                "Suspension date cannot be earlier "
                "than contract start date."))

    def validate_suspension_rules(self) -> None:
        """
        Refined Business Rules:
        1. By Request: No Monthly Bills must exist >= Effective Date.
        2. Maintenance: No validation required.
        3. Other Administrative: Validate debt threshold
        relative to Effective Date.
        """
        if (
            self.suspension_type == "Administrative" and
            self.reason == "Maintenance"
        ):
            return

        settings = frappe.get_doc("Billing Settings")
        eff_date = getdate(self.effective_date)

        if self.suspension_type == "By Request":
            existing_bill = frappe.db.exists("Monthly Bill", {
                "service_contract": self.service_contract,
                "start_date": [">=", eff_date],
                "docstatus": ["!=", 2]
            })

            if existing_bill:
                frappe.throw(_(
                    "Cannot suspend retroactively to {0}. "
                    "Monthly Bill {1} already exists "
                    "within or after this period. "
                    "Cancel the bills first or adjust the Effective Date."
                ).format(frappe.utils.formatdate(eff_date), existing_bill))

            previous_debts = frappe.get_all("Debt Ledger Entry", filters={
                "service_contract": self.service_contract,
                "status": ["in", ["Unpaid", "Partially Paid"]],
                "due_date": ["<", eff_date],
                "docstatus": 1
            })
            if previous_debts:
                frappe.throw(_(
                    "Subscriber has unpaid debts prior to "
                    "the requested suspension date."))

        elif self.suspension_type == "Administrative":
            all_unpaid_debts = frappe.get_all(
                "Debt Ledger Entry",
                filters={
                    "service_contract": self.service_contract,
                    "entry_type": "Monthly Fee",
                    "status": ["in", ["Unpaid", "Partially Paid"]],
                    "docstatus": 1
                },
                fields=["due_date", "outstanding_amount"]
            )

            grace_days = flt(settings.grace_period or 0)

            expired_debts = [
                d for d in all_unpaid_debts
                if eff_date > getdate(add_days(d.due_date, grace_days))
            ]

            total_expired_sum = sum(flt(d.outstanding_amount)
                                    for d in expired_debts)

            if total_expired_sum <= 0.01:
                frappe.throw(_(
                    "Administrative suspension requires expired "
                    "debts as of the Effective Date."))

            limit_months = int(settings.suspension_months_limit or 2)
            if len(expired_debts) < limit_months:
                frappe.throw(_(
                    "Threshold not met at {0}. Required: {1} months. "
                    "Current expired: {2}."
                    ).format(formatdate(eff_date),
                             limit_months, len(expired_debts)))

            min_debt = flt(settings.min_debt_for_suspension or 0)
            if total_expired_sum < min_debt:
                frappe.throw(_(
                    "Total expired debt ({0}) is below "
                    "the minimum threshold ({1}).")
                    .format(fmt_money(total_expired_sum),
                            fmt_money(min_debt)))

    def validate_technical_execution(self) -> None:
        """Validates final readings if the service is metered."""
        if self.billing_basis == "Metered":
            if not self.final_reading:
                frappe.throw(_(
                    "Final Reading is mandatory "
                    "for metered services."))

            last_reading = frappe.db.get_value(
                "Meter Reading",
                {"service_contract": self.service_contract, "docstatus": 1},
                "current_reading", order_by="reading_date desc, creation desc")

            if last_reading and flt(self.final_reading) < flt(last_reading):
                frappe.throw(_(
                    "Final reading ({0}) "
                    "cannot be lower than the last "
                    "recorded reading ({1}).")
                    .format(self.final_reading, last_reading))

    def on_submit(self) -> None:
        """Transitions status to Scheduled for the field team."""
        if self.status == "Draft":
            self.db_set("status", "Scheduled")

    def on_cancel(self) -> None:
        """
        Reverts the technical cut, restores contract to Active,
        and clears all suspension-related flags.
        """
        update_contract_property(
            service_contract=self.service_contract,
            update_type="Status",
            data={
                "new_status": "Active",
                "suspension_reason": None,
                "date": today(),
                "description": _(
                    "Suspension order {0} cancelled. "
                    "Restoring activity markers.").format(self.name)
            }
        )

        frappe.db.set_value("Service Contract", self.service_contract, {
            "suspended_since": None,
            "suspension_reason": ""
        })

        self.cancel_linked_meter_readings()
        self.db_set("status", "Draft")

    def cancel_linked_meter_readings(self) -> None:
        """
        Finds and cancels any submitted Meter Reading created
        by this suspension order.
        """
        linked_readings = frappe.get_all(
            "Meter Reading",
            filters={
                "service_contract": self.service_contract,
                "docstatus": 1,
                "remarks": ["like", f"%{self.name}%"]
            },
            pluck="name"
        )

        for reading_name in linked_readings:
            try:
                reading_doc = frappe.get_doc("Meter Reading", reading_name)
                reading_doc.cancel()
                frappe.msgprint(_("Meter Reading {0} has been cancelled.")
                                .format(reading_name), alert=True)
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=_(
                        "Error cancelling meter reading {0} "
                        "during suspension rollback").format(reading_name)
                )

    @frappe.whitelist()
    def execute_suspension_logic(
        self,
        final_reading: float,
        executed_date: str
    ) -> None:
        """
        Finalizes the technical process.

        Updates the Service Contract status to 'Suspended' and mirrors
        the specific reason for better administrative visibility.
        """
        self.final_reading = flt(final_reading)
        self.executed_date = executed_date
        self.status = "Executed"
        self.validate_technical_execution()

        update_contract_property(
            service_contract=self.service_contract,
            update_type="Status",
            data={
                "new_status": "Suspended",
                "suspension_reason": self.reason,
                "date": self.executed_date,
                "description": _(
                    "Service suspended technically on {0}. "
                    "Effective since {1}."
                    ).format(
                    formatdate(self.executed_date),
                    formatdate(self.effective_date)
                )
            }
        )

        frappe.db.set_value("Service Contract", self.service_contract, {
            "suspended_since": self.effective_date,
            "reactivation_date": None
        })

        if self.billing_basis == "Metered":
            self.create_technical_reading()

        self.save()

    def create_technical_reading(self) -> None:
        """Generates a Meter Reading document to stop the billing cycle."""
        reading = frappe.new_doc("Meter Reading")
        reading.service_contract = self.service_contract
        reading.reading_date = self.reading_date
        reading.current_reading = self.final_reading
        reading.remarks = _(
            "Closure reading (Suspension {0})"
            ).format(self.name)
        reading.insert(ignore_permissions=True)
        reading.submit()
