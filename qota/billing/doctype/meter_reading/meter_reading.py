# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, today

class MeterReading(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        consumption: DF.Float
        current_reading: DF.Float
        full_name: DF.Data | None
        premises: DF.Link | None
        previous_reading: DF.Float
        reading_date: DF.Date
        service_contract: DF.Link
        subscriber: DF.Link | None
    # end: auto-generated types

    def validate(self):
        # 1. Cargar configuraciones globales
        self.settings = frappe.get_doc("Billing Settings")
        
        # 2. Lógica de validación
        self.get_previous_reading()
        self.calculate_consumption()
        self.check_chronology()
        self.check_duplicate_reading_in_window()

    def get_previous_reading(self):
        """Busca el valor de la lectura anterior de forma automática"""
        # Buscamos la última lectura sometida (docstatus=1) para este contrato
        last_reading = frappe.db.get_value("Meter Reading", 
            {"service_contract": self.service_contract, "docstatus": 1, "name": ["!=", self.name]}, 
            "current_reading", order_by="reading_date desc")

        if last_reading is not None:
            self.previous_reading = flt(last_reading)
        else:
            # Si no hay lecturas previas, usamos la lectura inicial definida en el contrato
            self.previous_reading = frappe.db.get_value("Service Contract", 
                self.service_contract, "start_reading") or 0

    def calculate_consumption(self):
        """Calcula m³ y valida que el valor sea positivo"""
        curr = flt(self.current_reading)
        prev = flt(self.previous_reading)

        if curr < prev:
            frappe.throw(_("Error! Current reading ({0}) cannot be lower than previous reading ({1}).")
                         .format(curr, prev))
        
        self.consumption = curr - prev

    def check_chronology(self):
        """Evita meter una lectura con fecha anterior a una ya existente"""
        newer_reading = frappe.db.exists("Meter Reading", {
            "service_contract": self.service_contract,
            "reading_date": [">", self.reading_date],
            "docstatus": 1,
            "name": ["!=", self.name]
        })
        if newer_reading:
            frappe.throw(_("Chronology Error: A newer reading already exists ({0}). Readings must be entered in order.")
                         .format(newer_reading))

    def check_duplicate_reading_in_window(self):
        """Evita duplicados según la ventana de días en Billing Settings"""
        window = self.settings.reading_window_days or 5
        start_range = add_days(self.reading_date, -window)
        end_range = add_days(self.reading_date, window)

        duplicate = frappe.db.exists("Meter Reading", {
            "service_contract": self.service_contract,
            "reading_date": ["between", [start_range, end_range]],
            "docstatus": ["!=", 2],
            "name": ["!=", self.name]
        })

        if duplicate:
            frappe.throw(_("Duplicate Error: Another reading exists within the {0}-day window (Check: {1})")
                         .format(window, duplicate))