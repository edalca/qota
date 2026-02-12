# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

class Premises(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        address_reference: DF.SmallText | None
        block: DF.Data
        house_number: DF.Data
        sector: DF.Data
        status: DF.Literal["Active", "Inactive"]
    # end: auto-generated types

    def validate(self):
        # Evitar duplicados físicos por dirección
        self.validate_unique_location()
        
        # Bloquear cambios en campos permanentes tras el guardado inicial
        if not self.is_new():
            self.check_immutable_fields()

    def validate_unique_location(self):
        exists = frappe.db.exists("Premises", {
            "block": self.block,
            "house_number": self.house_number,
            "name": ["!=", self.name]
        })
        if exists:
            frappe.throw(_("Location ( Block, House) is already registered under ID {0}").format(exists))

    def check_immutable_fields(self):
        immutable_fields = ["registration_id","block", "house_number"]
        db_doc = frappe.get_doc("Premises", self.name)
        
        for field in immutable_fields:
            if self.get(field) != db_doc.get(field):
                frappe.throw(_("Field '{0}' is permanent and cannot be changed.").format(self.meta.get_label(field)))
                
@frappe.whitelist()
def premises_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Buscador optimizado para Premises: ID y Ubicación Concatenada.
    """
    search_txt = f"%{txt}%"
    
    # Ajustamos el CONCAT del WHERE y usamos parámetros para mayor seguridad
    query = f"""
        SELECT 
            p.name,
            CONCAT('S: ', p.sector, ' | B: ', p.block, ' | C: ', p.house_number) as location
        FROM 
            `tabPremises` p
        WHERE 
            p.docstatus = %s
            AND p.status = %s
            AND (
                p.name LIKE %s OR 
                p.sector LIKE %s OR
                p.block LIKE %s OR
                p.house_number LIKE %s OR
                CONCAT(p.sector, ' ', p.block, ' ', p.house_number) LIKE %s
            )
        ORDER BY p.name ASC
        LIMIT %s, %s
    """

    # Pasamos los parámetros por separado para evitar inyecciones SQL
    return frappe.db.sql(query, (
        filters.get('docstatus', 0), 
        filters.get('status', 'Active'),
        search_txt, search_txt, search_txt, search_txt, search_txt,
        int(start), int(page_len)
    ))