# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate
from dateutil.relativedelta import relativedelta
from frappe.model.document import Document


class BillingEntry(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from qota.billing.doctype.billing_entry_line.billing_entry_line import BillingEntryLine

		additional_fees: DF.Currency
		billing_month: DF.Literal["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
		billing_year: DF.Link | None
		consumption: DF.Float
		contract: DF.Link | None
		current_reading: DF.Float
		due_date: DF.Date | None
		excess_charge: DF.Currency
		fixed_charge: DF.Currency
		lines: DF.Table[BillingEntryLine]
		meter_reading: DF.Link | None
		posting_date: DF.Date
		premises: DF.Link | None
		previous_balance: DF.Currency
		previous_reading: DF.Float
		source_reference: DF.DynamicLink | None
		source_type: DF.Literal["Service Bill", "Billing Cycle"]
		status: DF.Literal["Unpaid", "Paid", "Overdue"]
		subscriber: DF.Link | None
		subscriber_name: DF.Data | None
		total_amount: DF.Currency
		total_discount: DF.Currency
	# end: auto-generated types

	pass

def make_billing_entry(contract, month, year, posting_date, source_type, source_name):
    """
    Función maestra para crear cobros. 
    Centraliza la lógica para evitar discrepancias entre cobros manuales y masivos.
    """
    # 0. Validar duplicados antes de procesar nada
    if check_existing_entry(contract, month, year):
        return None

    settings = frappe.get_doc("Billing Settings")
    contract_doc = frappe.get_doc("Contract", contract)
    tariff = frappe.get_doc("Tariff", contract_doc.tariff)
    subscriber = frappe.get_doc("Subscriber", contract_doc.subscriber)

    # 1. Calcular Cargos de Agua (Base + Exceso)
    water_data = calculate_water_charges(contract_doc, tariff, settings, month, year)
    
    # 2. Iniciar el documento Billing Entry
    entry = frappe.new_doc("Billing Entry")
    entry.update({
        "contract": contract,
        "billing_month": month,
        "billing_year": year,
        "posting_date": posting_date,
        "due_date": add_days(posting_date, settings.days_until_due),
        "source_type": source_type,
        "source_reference": source_name,
        "meter_reading": water_data.get('reading_ref'),
        "previous_reading": water_data.get('prev_val', 0),
        "current_reading": water_data.get('curr_val', 0),
        "consumption": water_data.get('consumption', 0),
        "fixed_charge": water_data['fixed_charge'],
        "excess_charge": water_data['excess_charge'],
        "status": "Unpaid"
    })

    # 3. Construcción del Desglose (Lines)
    water_subtotal = water_data['fixed_charge'] + water_data['excess_charge']
    
    # A. Línea de Servicio de Agua
    entry.append("lines", {
        "item_name": settings.water_service_label,
        "amount": water_subtotal
    })

    # B. Cargos Adicionales (Basura, etc.)
    extra_fees_total = 0
    for extra in tariff.get("additional_monthly_fees", []):
        fee_amt = flt(extra.amount)
        entry.append("lines", {
            "item_name": extra.fee_name,
            "amount": fee_amt
        })
        extra_fees_total += fee_amt

    # C. Aplicación de Descuentos Sociales y Contractuales
    total_discount = 0
    if tariff.allow_social_discounts:
        discount_data = get_applicable_discounts(subscriber, contract_doc, water_subtotal)
        if discount_data['amount'] > 0:
            entry.append("lines", {
                "item_name": discount_data['label'],
                "amount": -discount_data['amount'] # Negativo para el desglose
            })
            total_discount = discount_data['amount']

    # 4. Totales Finales del Encabezado
    entry.total_discount = total_discount
    entry.additional_fees = extra_fees_total
    entry.total_amount = (water_subtotal - total_discount) + extra_fees_total
    
    entry.insert(ignore_permissions=True)
    return entry

# --- FUNCIONES DE APOYO ---

def calculate_water_charges(contract, tariff, settings, month, year):
    """Calcula el consumo y el cargo por exceso basado en medidor"""
    res = {
        "fixed_charge": flt(tariff.fixed_fee),
        "excess_charge": 0,
        "consumption": 0,
        "reading_ref": None,
        "prev_val": 0,
        "curr_val": 0
    }

    if tariff.is_metered:
        window = flt(settings.reading_window_days) or 5
        # Buscamos la lectura que coincida con el contrato y el periodo
        reading = frappe.db.get_value("Meter Reading", {
            "contract": contract.name,
            "docstatus": 1,
            "billing_month": month, # Asumiendo que Meter Reading tiene estos campos
            "billing_year": year
        }, ["name", "previous_reading", "current_reading", "consumption"], as_dict=True)

        if reading:
            res["reading_ref"] = reading.name
            res["prev_val"] = reading.previous_reading
            res["curr_val"] = reading.current_reading
            res["consumption"] = reading.consumption
            
            if reading.consumption > tariff.base_consumption_limit:
                excess_qty = reading.consumption - tariff.base_consumption_limit
                res["excess_charge"] = excess_qty * flt(tariff.excess_fee_per_m3)
    
    return res

def get_applicable_discounts(subscriber, contract, water_amount):
    """Calcula el descuento de mayor jerarquía y suma beneficios del contrato"""
    # 1. Descuento de Edad (Solo el mayor)
    age_discount_pct = 0
    discount_label = "Social Discount"
    
    if subscriber.date_of_birth:
        age = relativedelta(getdate(), getdate(subscriber.date_of_birth)).years
        best_rule = frappe.get_all("Discount Rule", 
            filters={"condition_type": "Age", "min_age": ["<=", age]},
            fields=["discount_percentage", "discount_name"],
            order_by="discount_percentage desc",
            limit=1
        )
        if best_rule:
            age_discount_pct = flt(best_rule[0].discount_percentage)
            discount_label = best_rule[0].discount_name

    # 2. Beneficios manuales agregados al contrato
    manual_discount_pct = 0
    for benefit in contract.get("applied_benefits", []):
        manual_discount_pct += flt(benefit.discount_percentage)

    total_pct = age_discount_pct + manual_discount_pct
    return {
        "amount": water_amount * (total_pct / 100),
        "label": discount_label if age_discount_pct > 0 else "Contractual Benefit"
    }

def check_existing_entry(contract, month, year):
    """Evita duplicidad de cobros en el mismo periodo"""
    return frappe.db.exists("Billing Entry", {
        "contract": contract,
        "billing_month": month,
        "billing_year": year,
        "docstatus": ["<", 2]
    })