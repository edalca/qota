# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

class ConnectionFee(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        description: DF.SmallText | None
        disabled: DF.Check
        fee_name: DF.Data
        service_category: DF.Link
        total_fee: DF.Currency
    # end: auto-generated types

    def validate(self):
        self.validate_values()
        # Validar que solo haya una tarifa activa por categoría
        self.check_unique_active_fee()

    def validate_values(self):
        if self.total_fee <= 0:
            frappe.throw(_("The total connection fee must be greater than zero."))

    def check_unique_active_fee(self):
        """
        Asegura que solo exista un 'Connection Fee' activo POR CATEGORÍA.
        Si ya existe uno activo para 'Residencial', no deja crear otro hasta desactivar el anterior.
        """
        if not self.disabled:
            existing_active = frappe.db.exists("Connection Fee", {
                "disabled": 0,
                "service_category": self.service_category, # Filtramos por la misma categoría
                "name": ["!=", self.name] # Excluir el documento actual (por si es una edición)
            })
            
            if existing_active:
                frappe.throw(
                    _("There is already an active Connection Fee ({0}) for Service Category '{1}'. Please disable the existing one first.")
                    .format(existing_active, self.service_category)
                )

