# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today, add_days
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
        final_reading: DF.Float
        full_name: DF.Data | None
        premises: DF.Link | None
        reading_date: DF.Date | None
        reason: DF.Literal["Arrears", "Subscriber Request", "Fraud / Bypass", "Sanction", "Maintenance", "Other"]
        remarks: DF.SmallText | None
        service_contract: DF.Link
        status: DF.Literal["Draft", "Scheduled", "Executed"]
        subscriber: DF.Link | None
        suspension_date: DF.Date
        suspension_type: DF.Literal["Administrative", "By Request"]
    # end: auto-generated types

    def validate(self) -> None:
        """Main validation entry point."""
        self.validate_contract_eligibility()
        self.validate_suspension_date()
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

    def validate_suspension_date(self) -> None:
        """Ensures the suspension date is not before the contract start."""
        start_date = frappe.db.get_value("Service Contract",
                                         self.service_contract, "start_date")
        if getdate(self.suspension_date) < getdate(start_date):
            frappe.throw(_(
                "Suspension date cannot be earlier "
                "than contract start date."))

    def validate_suspension_rules(self) -> None:
        """
        Enforces business rules using Python logic and ORM
        for better readability.
        """
        settings = frappe.get_doc("Billing Settings")

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

        expired_debts = [
            d for d in all_unpaid_debts
            if getdate(today()) > getdate(add_days(d.due_date,
                                                   flt(settings.grace_period
                                                       or 0)))
        ]

        expired_months_count = len(expired_debts)
        total_expired_sum = sum(flt(d.outstanding_amount)
                                for d in expired_debts)

        # A. CASO: BY REQUEST (Voluntario)
        if self.suspension_type == "By Request":
            # Para cierre voluntario, sumamos TODO lo pendiente (vencido o no)
            total_current_debt = sum(flt(d.outstanding_amount) for d
                                     in all_unpaid_debts)

            if total_current_debt > 0.01:
                frappe.throw(_(
                    "Voluntary suspension denied. "
                    "Subscriber must pay all debts ({0}) first."
                ).format(frappe.format_value(total_current_debt, "Currency")))

        # B. CASO: ADMINISTRATIVE (Involuntario)
        elif self.suspension_type == "Administrative":
            if self.reason == "Maintenance":
                return

            if total_expired_sum <= 0.01:
                frappe.throw(_(
                    "Administrative suspension is not allowed for "
                    "accounts that are up to date."))

            if (
                expired_months_count <
                int(settings.suspension_months_limit or 2)
            ):
                frappe.throw(_(
                    "Threshold not met. Required: {0} months. "
                    "Current expired: {1}.")
                             .format(settings.suspension_months_limit,
                                     expired_months_count))

            if total_expired_sum < flt(settings.min_debt_for_suspension or 0):
                frappe.throw(_("Debt ({0}) is below minimum threshold ({1}).")
                             .format(frappe.format_value(total_expired_sum,
                                                         "Currency"),
                                     frappe.format_value(
                                         settings.min_debt_for_suspension,
                                         "Currency")))

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
        """Reverts the technical cut and restores contract to Active."""
        update_contract_property(
            service_contract=self.service_contract,
            update_type="Status",
            data={
                "new_status": "Active",
                "suspension_reason": None,
                "date": today(),
                "description": _("Suspension order {0} cancelled.")
                .format(self.name)
            }
        )
        self.db_set("status", "Draft")

    @frappe.whitelist()
    def execute_suspension_logic(
        self,
        final_reading: float,
        reading_date: str
    ) -> None:
        """
        Finalizes the technical process.

        Updates the Service Contract status to 'Suspended' and mirrors
        the specific reason for better administrative visibility.
        """
        self.final_reading = flt(final_reading)
        self.reading_date = reading_date
        self.status = "Executed"
        self.validate_technical_execution()

        update_contract_property(
            service_contract=self.service_contract,
            update_type="Status",
            data={
                "new_status": "Suspended",
                "suspension_reason": self.reason,
                "date": self.reading_date,
                "description": _("Service suspended by technical order {0}")
                .format(self.name)
            }
        )

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
