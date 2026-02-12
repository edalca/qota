# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
import json  
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, getdate 

from qota.billing.utils import make_debt_ledger_entry

class ServiceContract(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        billing_basis: DF.Literal["Flat Rate", "Metered"]
        cistern_capacity: DF.Float
        connection_fee: DF.Link
        connection_fee_posted: DF.Check
        end_date: DF.Date | None
        full_name: DF.Data | None
        has_cistern: DF.Check
        last_status_change: DF.Date | None
        meter_id: DF.Data | None
        premises: DF.Link
        service_category: DF.Link
        start_date: DF.Date
        start_reading: DF.Float
        status: DF.Literal["Active", "Suspended", "Closed", "Cancelled"]
        subscriber: DF.Link
        total_connection_fee: DF.Data | None
    # end: auto-generated types

    def validate(self):
        # Evitar duplicados activos para el mismo predio
        self.check_active_contract_on_save()

    def check_active_contract_on_save(self):
        if self.status == "Active":
            existing = frappe.db.exists("Service Contract", {
                "premises": self.premises,
                "status": "Active",
                "docstatus": ["<", 2],
                "name": ["!=", self.name]
            })
            if existing:
                frappe.throw(
                    _("The Premises {0} is already associated with an Active contract: {1}.")
                    .format(self.premises, existing)
                )

    def on_submit(self):
        """
        Activa el contrato, genera la deuda de conexión y registra en el log.
        """
        # 1. Actualizar estado
        self.db_set("status", "Active")
        self.db_set("last_status_change", today())

        # 2. Lógica de Cobro de Conexión (Minimalista)
        if self.connection_fee and not self.connection_fee_posted:
            self.post_connection_debt()

        # 3. Crear registro de Log
        log = frappe.new_doc("Service Contract Log")
        log.service_contract = self.name
        log.operation_date = today()
        log.change_type = "Status Change"
        log.field_changed = "Contract Status"
        log.description = _("Initial contract activation and validation.")
        log.insert(ignore_permissions=True)

    def post_connection_debt(self):
        """
        Llama al motor de deudas sin preocuparse por años o meses.
        """
        fee_amount = frappe.db.get_value("Connection Fee", self.connection_fee, "total_fee")
        
        if fee_amount and fee_amount > 0:
            # LLAMADA SIMPLIFICADA: Sin Year ni Month
            make_debt_ledger_entry(
                contract_name=self.name,
                entry_type="Connection Fee",
                amount=fee_amount,
                ref_dt="Service Contract",
                ref_dn=self.name,
                description=_("Connection Fee - Contract Activation")
            )
            
            # Marcar como posteado
            self.db_set("connection_fee_posted", 1)
            
            frappe.msgprint(
                _("Connection Fee of {0} has been registered as a pending debt.").format(
                    frappe.format(fee_amount, "Currency")
                ),
                indicator='blue'
            )

@frappe.whitelist()
def update_contract_property(contract_id, update_type, data):
    """
    Whitelisted function for quick UI actions (Modals).
    """
    if isinstance(data, str):
        data = json.loads(data)
        
    doc = frappe.get_doc("Service Contract", contract_id)
    log = frappe.new_doc("Service Contract Log")
    log.service_contract = contract_id
    log.operation_date = data.get("date") or today()
    log.description = data.get("description")
    
    if update_type == "Cistern":
        doc.has_cistern = data.get("has_cistern")
        doc.cistern_capacity = data.get("capacity") if doc.has_cistern else 0
        log.change_type = "Cistern Update"
        log.field_changed = "Cistern Status"
        
    elif update_type == "Billing":
        doc.billing_basis = data.get("billing_basis")
        if doc.billing_basis == "Metered":
            doc.meter_id = data.get("meter_id")
            doc.start_reading = data.get("start_reading")
        else:
            doc.meter_id = ""
            doc.start_reading = 0
        log.change_type = "Billing Basis Change"
        log.field_changed = "Billing Basis"

    elif update_type == "Status":
        doc.status = data.get("new_status")
        doc.last_status_change = log.operation_date
        if doc.status == "Closed":
            doc.end_date = log.operation_date
        log.change_type = "Status Change"
        log.field_changed = "Contract Status"

    log.insert(ignore_permissions=True)
    doc.flags.ignore_permissions = True
    doc.save()
    return _("Contract updated successfully")

@frappe.whitelist()
def contract_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Custom search query for Service Contract selection.
    """
    search_txt = f"%{txt}%"
    conditions = []
    
    # Handle docstatus
    docstatus = filters.get('docstatus', 1)
    conditions.append(f"sc.docstatus = {docstatus}")

    # Handle status filtering
    if filters and 'status' in filters:
        status_filter = filters.get('status')
        if isinstance(status_filter, (list, tuple)):
            if status_filter[0] == 'in':
                values = status_filter[1]
                formatted_values = ", ".join([frappe.db.escape(v) for v in values])
                conditions.append(f"sc.status IN ({formatted_values})")
        else:
            conditions.append(f"sc.status = {frappe.db.escape(status_filter)}")
    else:
        conditions.append("sc.status = 'Active'")

    # Handle billing basis filter
    if filters and 'billing_basis' in filters:
        conditions.append(f"sc.billing_basis = {frappe.db.escape(filters.get('billing_basis'))}")

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT 
            sc.name, 
            sc.full_name, 
            CONCAT('B: ', p.block, ' | C: ', p.house_number) as location
        FROM 
            `tabService Contract` sc
        JOIN 
            `tabPremises` p ON sc.premises = p.name
        WHERE 
            {where_clause}
            AND (
                sc.name LIKE {frappe.db.escape(search_txt)} OR 
                sc.full_name LIKE {frappe.db.escape(search_txt)} OR
                p.block LIKE {frappe.db.escape(search_txt)} OR
                p.house_number LIKE {frappe.db.escape(search_txt)}
            )
        ORDER BY sc.name ASC
        LIMIT {start}, {page_len}
    """

    return frappe.db.sql(query)

@frappe.whitelist()
def service_contract_data(service_contract):
    # Convertimos a json.loads si viene como string, o aseguramos que sea lista
    if isinstance(service_contract, str):
        import json
        service_contract = json.loads(service_contract)
    
    if not service_contract:
        return []

    SQL = """
    SELECT 
        sc.name,
        sc.full_name, 
        p.block,
        p.house_number as house
    FROM `tabService Contract` sc 
    LEFT JOIN `tabPremises` p ON sc.premises = p.name
    WHERE sc.name IN %s
    """     
    return frappe.db.sql(SQL, (tuple(service_contract),), as_dict=True)