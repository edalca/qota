"""Convert only proven legacy suspension types before model synchronization."""

import frappe
from frappe.modules.patch_handler import PatchError
from qota.migration_identity import historical_completion


def execute():
    if historical_completion("qota.patches.collapse_suspension_reason"):
        return
    _migrate()


def _migrate():
    if not frappe.db.has_column("Service Suspension", "reason"):
        return
    # Frappe retains removed columns. A residual reason is not a legacy type.
    rows = frappe.db.sql("SELECT name,suspension_type,reason,service_contract FROM `tabService Suspension` "
        "WHERE suspension_type IN ('Administrative','By Request') ORDER BY name FOR UPDATE", as_dict=True)
    changes = []
    for row in rows:
        if row.reason in ("Fraud / Bypass", "Sanction"):
            # Never manufacture a fine or convert an unsupported relationship.
            fine = (frappe.db.get_value("Service Suspension", row.name, "service_fine")
                if frappe.db.has_column("Service Suspension", "service_fine") else None)
            valid = fine and frappe.db.get_value("Service Fine", fine,
                ["docstatus", "service_contract", "status"], as_dict=True)
            if not valid or valid.docstatus != 1 or valid.service_contract != row.service_contract or valid.status != "Unpaid":
                raise PatchError(f"LegacySuspensionFineUnproven: {row.name}")
            kind = "By Fine"
        elif row.suspension_type == "By Request" or row.reason in ("Subscriber Request", "Maintenance"):
            kind = "Subscriber Request"
        elif row.reason in ("Arrears", "Other", "", None):
            kind = "Arrears"
        else:
            raise PatchError(f"LegacySuspensionReasonUnknown: {row.name}")
        changes.append((row.name, kind))
    for name, kind in changes:
        frappe.db.set_value("Service Suspension", name, "suspension_type", kind, update_modified=False)
