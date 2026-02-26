# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

# Centralized imports
from qota.billing.doctype.debt_ledger_entry.debt_ledger_entry import (
    make_debt_ledger_entry,
    clear_and_delete_debt
)
from qota.governance.doctype.service_contract.service_contract import (
    update_contract_property
)


class ServiceReconnection(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        billing_basis: DF.Literal["", "Flat Rate", "Metered"]
        execution_date: DF.Date | None
        full_name: DF.Data | None
        initial_reading: DF.Float
        premises: DF.Link | None
        reconnection_fee: DF.Currency
        remarks: DF.SmallText | None
        service_contract: DF.Link
        status: DF.Literal["Draft", "Pending Payment", "Paid", "Scheduled", "Executed", "Cancelled"]
        subscriber: DF.Link | None
    # end: auto-generated types

    def validate(self) -> None:
        """Runs business logic before submission."""
        self.validate_contract_status()
        self.enforce_fee_rules()

    def validate_contract_status(self) -> None:
        """Ensures the contract is actually suspended."""
        status = frappe.db.get_value("Service Contract",
                                     self.service_contract,
                                     "status")
        if status != "Suspended":
            frappe.throw(_(
                "Contract {0} is not suspended. "
                "Reconnection not applicable.")
                .format(self.service_contract))

    def enforce_fee_rules(self) -> None:
        """
        Calculates the fee: 0 if the previous cut was Maintenance or
        By Request.
        Enforces zero even if manually changed in the UI.
        """
        last_suspension = frappe.db.get_value(
            "Service Suspension",
            {
                "service_contract": self.service_contract,
                "status": "Executed",
                "docstatus": 1
            },
            ["suspension_type", "reason"],
            as_dict=True,
            order_by="creation desc")

        if last_suspension:
            is_free = (
                last_suspension.suspension_type == "By Request" or
                last_suspension.reason == "Maintenance"
            )

            if is_free:
                self.reconnection_fee = 0
                if not self.remarks:
                    self.remarks = _(
                        "Free Reconnection: "
                        "Previous suspension was due to {0}."
                        ).format(last_suspension.reason)
            elif self.is_new() and not self.reconnection_fee:
                # Si no es gratis y es nuevo, jalamos la tarifa por defecto
                default_fee = frappe.db.get_single_value(
                    "Billing Settings",
                    "default_reconnection_fee")
                self.reconnection_fee = flt(default_fee)

    def on_submit(self) -> None:
        """
        Handles financial impact. If fee > 0, creates debt.
        If fee = 0, goes straight to Paid to allow immediate work.
        """
        if flt(self.reconnection_fee) > 0:
            self.db_set("status", "Pending Payment")
            make_debt_ledger_entry(
                contract_name=self.service_contract,
                entry_type="Reconnection Fee",
                amount=flt(self.reconnection_fee),
                ref_dt=self.doctype,
                ref_dn=self.name,
                description=_("Reconnection Fee - Order {0}").format(self.name)
            )
        else:
            self.db_set("status", "Paid")

    def on_cancel(self) -> None:
        """Cleans up financial records."""
        clear_and_delete_debt(self.doctype, self.name)
        self.db_set("status", "Cancelled")

    @frappe.whitelist()
    def execute_reconnection_logic(
        self,
        initial_reading: float,
        execution_date: str
    ) -> None:
        """
        Technically restores the water supply and reactivates the contract.
        """
        if self.status not in ["Paid", "Scheduled"]:
            frappe.throw(_(
                "Cannot execute. "
                "Payment is required for this reconnection."))

        self.initial_reading = flt(initial_reading)
        self.execution_date = execution_date
        self.status = "Executed"

        # Restore Contract Status
        update_contract_property(
            service_contract=self.service_contract,
            update_type="Status",
            data={
                "new_status": "Active",
                "date": self.execution_date,
                "suspension_reason": None,
                "description": _("Service restored via technical order {0}")
                .format(self.name)
            }
        )

        # Create meter reading if metered
        if self.billing_basis == "Metered":
            self.create_start_reading()

        self.save()

    def create_start_reading(self) -> None:
        """Starts the new billing cycle with a fresh reading."""
        reading = frappe.new_doc("Meter Reading")
        reading.service_contract = self.service_contract
        reading.reading_date = self.execution_date 
        reading.current_reading = self.initial_reading
        reading.remarks = _(
             "Start reading (Reconnection Order {0})"
             ).format(self.name)
        reading.insert(ignore_permissions=True)
        reading.submit()

