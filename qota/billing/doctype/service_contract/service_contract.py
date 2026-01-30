# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
import json  
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
        last_status_change: DF.Date | None
        meter_id: DF.Data | None
        premises: DF.Link
        service_category: DF.Link
        start_date: DF.Date
        start_reading: DF.Float
        status: DF.Literal["Active", "Suspended", "Closed", "Cancelled"]
        subscriber: DF.Link
    # end: auto-generated types

    def validate(self):
        # Evitar duplicados activos
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
        Se ejecuta cuando el usuario hace clic en 'Submit'.
        Establece el contrato como activo y crea el primer registro en el Log.
        """
        from frappe.utils import today
            
        # 1. Actualizamos el estado del contrato
        self.db_set("status", "Active")
        self.db_set("last_status_change", today())

        # 2. Creamos el registro automático en el Log
        log = frappe.new_doc("Service Contract Log")
        log.service_contract = self.name
        log.operation_date = today()
        log.change_type = "Status Change"
        log.field_changed = "Contract Status"
        log.description = _("Initial contract activation and validation.")
            
        # Insertamos el log ignorando permisos para que siempre se guarde
        log.insert(ignore_permissions=True)

@frappe.whitelist()
def update_contract_property(contract_id, update_type, data):
    """
    Esta es la función que el JS busca. Debe estar fuera de la clase.
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
    Buscador que muestra: ID, Nombre Completo y Ubicación Detallada (Sector, Bloque, Casa)
    """
    # 1. Escapamos el texto de búsqueda para evitar inyecciones
    search_txt = f"%{txt}%"
    
    # 2. Construimos la consulta SQL con un JOIN a la tabla de Inmuebles (Premises)
    # Usamos CONCAT para que la ubicación se vea en una sola columna bonita
    query = f"""
        SELECT 
            sc.name, 
            sc.full_name, 
            CONCAT('S: ', p.sector, ' | B: ', p.block, ' | C: ', p.house_number) as location
        FROM 
            `tabService Contract` sc
        JOIN 
            `tabPremises` p ON sc.premises = p.name
        WHERE 
            sc.docstatus = {filters.get('docstatus', 1)}
            AND sc.status = '{filters.get('status', 'Active')}'
            AND sc.billing_basis = '{filters.get('billing_basis', 'Metered')}'
            AND (
                sc.name LIKE {frappe.db.escape(search_txt)} OR 
                sc.full_name LIKE {frappe.db.escape(search_txt)} OR
                p.sector LIKE {frappe.db.escape(search_txt)} OR
                p.block LIKE {frappe.db.escape(search_txt)} OR
                p.house_number LIKE {frappe.db.escape(search_txt)}
            )
        ORDER BY sc.name ASC
        LIMIT {start}, {page_len}
    """

    return frappe.db.sql(query)