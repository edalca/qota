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
        area_sqm: DF.Float
        block: DF.Data
        house_number: DF.Data
        improvement_details: DF.SmallText | None
        meter_id: DF.Data | None
        nature: DF.Literal["Urban", "Rural"]
        registration_id: DF.Data | None
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
            "sector": self.sector,
            "block": self.block,
            "house_number": self.house_number,
            "name": ["!=", self.name]
        })
        if exists:
            frappe.throw(_("Location (Sector, Block, House) is already registered under ID {0}").format(exists))

    def check_immutable_fields(self):
        immutable_fields = ["registration_id", "sector", "block", "house_number"]
        db_doc = frappe.get_doc("Premises", self.name)
        
        for field in immutable_fields:
            if self.get(field) != db_doc.get(field):
                frappe.throw(_("Field '{0}' is permanent and cannot be changed.").format(self.meta.get_label(field)))