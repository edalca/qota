# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ServiceContractLog(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        change_type: DF.Literal["Cistern Update", "Billing Basis Change", "Status Change"]
        description: DF.SmallText | None
        field_changed: DF.Data | None
        operation_date: DF.Date
        service_contract: DF.Link
    # end: auto-generated types

    def validate(self):
        """
        Prevents modification of log entries after they are created to ensure 
        an immutable audit trail.
        """
        if not self.is_new():
            frappe.throw(_("Audit logs cannot be modified once they are created."))

    def on_trash(self):
        """
        Optional: Prevents deletion of logs for security purposes.
        If the administrator needs to delete them, this can be commented out.
        """
        if not "System Manager" in frappe.get_roles():
            frappe.throw(_("Only System Managers can delete audit logs."))

    def before_insert(self):
        """
        Ensures the user field is always populated with the current session user.
        """
        self.user = frappe.session.user