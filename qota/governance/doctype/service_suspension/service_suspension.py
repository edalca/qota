# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate,today
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
        reason: DF.Literal["Unpaid Debt", "Moving Out", "Empty House", "Temporary Absence", "Other"]
        remarks: DF.SmallText | None
        service_contract: DF.Link
        status: DF.Literal["Draft", "Scheduled", "Executed", "Reconnected"]
        subscriber: DF.Link | None
        suspension_date: DF.Date
        suspension_type: DF.Literal["Voluntary", "Involuntary"]
    # end: auto-generated types

    def validate(self) -> None:
        """
        Main validation entry point.
        """
        self.validate_contract_eligibility()
        self.validate_suspension_date()
        if self.status == "Executed":
            self.validate_technical_execution()

    def validate_contract_eligibility(self) -> None:
        """
        Checks if the contract is in a valid state to be suspended.
        """
        contract_data = frappe.db.get_value(
            "Service Contract",
            self.service_contract,
            ["status", "docstatus"],
            as_dict=True
        )

        if not contract_data:
            frappe.throw(_("The selected Service Contract does not exist."))

        if contract_data.docstatus != 1:
            frappe.throw(_(
                "The Service Contract must be "
                "submitted before suspension."
            ))

        if contract_data.status == "Suspended":
            frappe.throw(_("Contract {0} is already suspended.")
                         .format(self.service_contract))

        if contract_data.status in ["Closed", "Cancelled"]:
            frappe.throw(_("Cannot suspend a contract in '{0}' status.")
                         .format(contract_data.status))

        # Check for pending suspension orders
        pending_order = frappe.db.exists("Service Suspension", {
            "service_contract": self.service_contract,
            "status": ["in", ["Draft", "Scheduled"]],
            "name": ["!=", self.name],
            "docstatus": ["<", 2]
        })

        if pending_order:
            frappe.throw(
                _(
                    "There is already a pending suspension order ({0}) "
                    "for this contract.")
                .format(pending_order)
            )

    def validate_suspension_date(self) -> None:
        """
        Ensures the suspension date is not before the contract start date.
        """
        start_date = frappe.db.get_value("Service Contract",
                                         self.service_contract, "start_date")

        if getdate(self.suspension_date) < getdate(start_date):
            frappe.throw(
                _(
                    "Suspension date ({0}) cannot be earlier "
                    "than contract start date ({1}).")
                .format(self.suspension_date, start_date)
            )

    def validate_technical_execution(self) -> None:
        """
        Validates meter readings when the cut is executed.
        """
        if self.billing_basis == "Metered":
            if not self.final_reading:
                frappe.throw(_(
                    "Final Reading is mandatory for metered "
                    "services upon execution."))

            last_reading = frappe.db.get_value(
                "Meter Reading",
                {"service_contract": self.service_contract, "docstatus": 1},
                "current_reading",
                order_by="reading_date desc, creation desc"
            )

            if last_reading and self.final_reading < flt(last_reading):
                frappe.throw(
                    _(
                        "Final reading ({0}) cannot be lower than the last "
                        "recorded reading ({1}).")
                    .format(self.final_reading, last_reading)
                )

    def on_submit(self) -> None:
        """
        Sets status to Scheduled upon submission.
        """
        if self.status == "Draft":
            self.db_set("status", "Scheduled")

    def on_cancel(self) -> None:
        """
        Sets status to Draft upon cancellation.
        """
        if self.status == "Executed":
            self.db_set("status", "Draft")
        update_contract_property(
            contract_id=self.service_contract,
            update_type="Status",
            data={
                "new_status": "Active",
                "date": today(),
                "description": _("Service suspension cancelled {0}")
                .format(self.name)
            }
            )

    @frappe.whitelist()
    def execute_suspension_logic(
        self,
        final_reading: float,
        reading_date: str
    ) -> None:
        """
        Server-side trigger for technical confirmation.

        Updates the contract to 'Suspended' and logs the final reading.
        """
        self.final_reading = flt(final_reading)
        self.reading_date = reading_date
        self.status = "Executed"

        self.validate_technical_execution()

        update_contract_property(
            contract_id=self.service_contract,
            update_type="Status",
            data={
                "new_status": "Suspended",
                "date": self.reading_date,
                "description": _("Service suspended by order {0}")
                .format(self.name)
            }
        )

        if self.billing_basis == "Metered":
            self.create_technical_reading()

        self.save()

    def create_technical_reading(self) -> None:
        """
        Generates a Meter Reading document to close the consumption cycle.
        """
        reading = frappe.new_doc("Meter Reading")
        reading.service_contract = self.service_contract
        reading.reading_date = self.reading_date
        reading.current_reading = self.final_reading
        reading.remarks = _(
            "Closure reading due to suspension {0}").format(self.name)
        reading.insert(ignore_permissions=True)
        reading.submit()
