# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class ServiceContract(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        billing_basis: DF.Literal["Flat Rate", "Metered"]
        cistern_capacity: DF.Float
        end_date: DF.Date | None
        full_name: DF.Data | None
        has_cistern: DF.Check
        meter_id: DF.Data | None
        premises: DF.Link
        reactivation_date: DF.Date | None
        service_category: DF.Link
        start_date: DF.Date
        start_reading: DF.Float
        status: DF.Literal["Active", "Suspended", "Closed", "Cancelled"]
        subscriber: DF.Link
        suspended_since: DF.Date | None
        suspension_reason: DF.Data | None
    # end: auto-generated types

    def validate(self):
        self.check_active_contract_on_save()

    def on_submit(self):
        self.activate_contract()
        self.create_activation_log()

    def on_cancel(self):
        self.process_cancellation()

    def check_active_contract_on_save(self):
        """
        Ensures that a premise does not have more than one active contract.
        """
        if self.status == "Active":
            filters = {
                "premises": self.premises,
                "status": "Active",
                "docstatus": ["<", 2],
                "name": ["!=", self.name]
            }
            existing = frappe.db.exists("Service Contract", filters)
            if existing:
                msg = _("The Premises {0} is already associated with "
                        "an Active contract: {1}.")
                frappe.throw(msg.format(self.premises, existing))

    def activate_contract(self):
        """Sets the contract status to Active"""
        self.db_set("status", "Active")

    def create_activation_log(self):
        """Creates a log entry for the initial activation."""
        self.add_log_entry(
            change_type="Status Change",
            field="Contract Status",
            description=_("Initial contract activation and validation.")
        )

    def process_cancellation(self):
        """Updates status"""
        self.db_set("status", "Cancelled")

    def add_log_entry(self, change_type, field, description, op_date=None):
        """
        Helper method to create a Service Contract Log entry.
        """
        log = frappe.new_doc("Service Contract Log")
        log.service_contract = self.name
        log.operation_date = op_date or today()
        log.change_type = change_type
        log.field_changed = field
        log.description = description
        log.insert(ignore_permissions=True)


@frappe.whitelist()
def update_contract_property(
    service_contract: str,
    update_type: str,
    data
) -> str:
    """
    Whitelisted function for quick UI updates via Modals.

    Now supports tracking specific reasons for suspension to
    provide better visibility in the Service Contract list.

    Args:
        service_contract (str): The name of the Service Contract.
        update_type (str): Type of update (Cistern, Billing, Status).
        data (str/dict): JSON string or dict containing the update details.
    """
    if isinstance(data, str):
        data = json.loads(data)

    doc = frappe.get_doc("Service Contract", service_contract)
    op_date = data.get("date") or today()
    description = data.get("description")

    if update_type == "Cistern":
        doc.has_cistern = data.get("has_cistern")
        doc.cistern_capacity = data.get("capacity") if doc.has_cistern else 0
        doc.add_log_entry("Cistern Update", "Cistern Status", description)

    elif update_type == "Billing":
        doc.billing_basis = data.get("billing_basis")
        if doc.billing_basis == "Metered":
            doc.meter_id = data.get("meter_id")
            doc.start_reading = data.get("start_reading")
        else:
            doc.meter_id = ""
            doc.start_reading = 0
        doc.add_log_entry("Billing Basis Change", "Billing Basis", description)

    elif update_type == "Status":
        new_status = data.get("new_status")
        doc.status = new_status

        if new_status == "Suspended":
            doc.suspension_reason = data.get("suspension_reason")
        else:
            doc.suspension_reason = ""

        if new_status == "Closed":
            doc.end_date = op_date

        doc.add_log_entry("Status Change",
                          _("Status: {0}").format(_(new_status)),
                          description)

    doc.flags.ignore_permissions = True
    doc.save()

    return _("Contract updated successfully")


@frappe.whitelist()
def service_contract_query(doctype, txt, searchfield, start, page_len, filters):
    """Return Service Contract search results with premises info in the display label.

    Supports multi-token search: "15 10" matches contracts where one field contains
    "15" AND another contains "10", allowing combined block + house_number lookups.
    """
    if isinstance(filters, str):
        filters = frappe.parse_json(filters)

    conditions = [f"sc.docstatus = {int(filters.get('docstatus', 1))}"]
    status_filter = filters.get("status")
    if status_filter:
        if isinstance(status_filter, (list, tuple)) and status_filter[0] == "in":
            vals = ", ".join([frappe.db.escape(v) for v in status_filter[1]])
            conditions.append(f"sc.status IN ({vals})")
        else:
            conditions.append(f"sc.status = {frappe.db.escape(status_filter)}")
    else:
        conditions.append("sc.status = 'Active'")

    if filters.get("billing_basis"):
        conditions.append(f"sc.billing_basis = {frappe.db.escape(filters.get('billing_basis'))}")

    tokens = [t for t in (txt or "").split() if t]
    params = {"start": int(start), "page_len": int(page_len)}
    token_clauses = []
    for i, token in enumerate(tokens):
        key = f"tok{i}"
        params[key] = f"%{token}%"
        token_clauses.append(
            f"(sc.name LIKE %({key})s OR sc.full_name LIKE %({key})s"
            f" OR p.block LIKE %({key})s OR p.house_number LIKE %({key})s)"
        )

    where_clause = " AND ".join(conditions)
    search_clause = " AND ".join(token_clauses) if token_clauses else "1=1"
    block_label = _("Block")
    house_label = _("House")

    query = f"""
        SELECT
            sc.name,
            CONCAT(
                sc.full_name,
                ' ({block_label}: ', p.block, ' | {house_label}: ', p.house_number, ')'
            ) AS display_name
        FROM `tabService Contract` sc
        JOIN `tabPremises` p ON sc.premises = p.name
        WHERE {where_clause}
        AND ({search_clause})
        ORDER BY sc.name ASC
        LIMIT %(start)s, %(page_len)s
    """

    return frappe.db.sql(query, params)


@frappe.whitelist()
def service_contract_data(service_contract: str):
    """
    Fetches basic contract and premises data for a list of names.
    """
    if isinstance(service_contract, str):
        service_contract = json.loads(service_contract)

    if not service_contract:
        return []

    sql_query = """
        SELECT
            sc.name, sc.full_name, p.block, p.house_number as house
        FROM `tabService Contract` sc
        LEFT JOIN `tabPremises` p ON sc.premises = p.name
        WHERE sc.name IN %s
    """
    return frappe.db.sql(sql_query, (tuple(service_contract),), as_dict=True)
