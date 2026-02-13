# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

from typing import final
import frappe
from frappe import _
from frappe.utils import flt, getdate, today, date_diff, add_days,get_last_day


def make_debt_ledger_entry(contract_name, entry_type, amount, ref_dt=None, ref_dn=None, description=None, fiscal_month=None, fiscal_year=None):
    """
    Crea una deuda en el Ledger (Draft).
    - Si vienen fiscal_month/year: Usa esos datos (Ciclo de Facturación).
    - Si NO vienen: Usa el mes y año actual (Connection Fee, Multas, etc).
    """
    
    if flt(amount) <= 0:
        frappe.throw(_("Amount must be greater than zero to create a Debt Ledger Entry."))

    # ---------------------------------------------------------
    # 1. LÓGICA DEL BILLING PERIOD (MM-YYYY)
    # ---------------------------------------------------------
    if fiscal_month and fiscal_year:
        # Caso A: Viene de un Ciclo de Facturación específico
        m = int(fiscal_month)
        y = int(fiscal_year)
    else:
        # Caso B: Cobro manual o Fee único -> Usamos la fecha de HOY
        current_date = getdate(today())
        m = current_date.month
        y = current_date.year

    # Formateamos siempre a "03-2026" (con cero a la izquierda si hace falta)
    billing_period = f"{m:02d}-{y}"

    # ---------------------------------------------------------
    # 2. CONFIGURACIÓN DE VENCIMIENTOS
    # ---------------------------------------------------------
    settings = frappe.get_doc("Billing Settings")
    
    days_to_add = 0
    if entry_type == "Connection Fee":
        days_to_add = settings.connection_debt_deadline_days or 30
    elif entry_type == "Monthly Fee":
        days_to_add = settings.days_until_due or 15
    else:
        days_to_add = settings.grace_period or 0

    calculated_due_date = add_days(today(), days_to_add)

    # ---------------------------------------------------------
    # 3. CREAR DOCUMENTO
    # ---------------------------------------------------------
    debt = frappe.get_doc({
        "doctype": "Debt Ledger Entry",
        "service_contract": contract_name,
        "entry_type": entry_type,
        "amount": flt(amount),
        "due_date": calculated_due_date,
        "paid_amount": 0,
        "outstanding_amount": flt(amount),
        "reference_doctype": ref_dt,
        "reference_name": ref_dn,
        "description": description,
        "status": "Unpaid",
        "billing_period": billing_period
    })
    
    debt.insert(ignore_permissions=True)
    
    return debt


@frappe.whitelist()
def get_monthly_billing_breakdown(contract_name, billing_month, billing_year, start_date, end_date):
    """
    Core Billing Engine.
    Adjusts billing days based on the Service Contract's actual start date
    and month-specific duration.
    """
    contract = frappe.get_doc("Service Contract", contract_name)
    settings = frappe.get_doc("Billing Settings")
    
    # 1. CROSS-REFERENCE WITH CONTRACT START DATE
    period_start = getdate(start_date)
    contract_start = getdate(contract.start_date)
    
    # Calculate the actual day we start charging
    actual_billing_start = max(period_start, contract_start)
    
    # Safety check: if contract hasn't started yet
    if actual_billing_start > getdate(end_date):
        return {
            "total_to_bill": 0.0,
            "detailed_items": [],
            "total_days": 0
        }

    # 2. CALCULATE DAYS IN THIS SPECIFIC MONTH (Dynamic)
    last_day_of_month = get_last_day(actual_billing_start)
    days_in_this_month = getdate(last_day_of_month).day 
    
    # 3. CALCULATE ACTUAL DAYS SERVED
    total_days = date_diff(end_date, actual_billing_start) + 1
    
    # 4. DYNAMIC PRORATION FACTOR
    if total_days >= days_in_this_month:
        proration_factor = 1.0
    else:
        proration_factor = flt(total_days) / flt(days_in_this_month)
    
    # 5. GET ACTIVE RATE
    service_rate = get_active_service_rate(contract.service_category, end_date)
    proration_factor=1
    # 6. CALCULATE BASE AMOUNTS
    if contract.billing_basis == "Flat Rate":
        base_results = calculate_flat_rate(contract, service_rate, settings, proration_factor, total_days)
    elif contract.billing_basis == "Metered":
        base_results = calculate_metered_rate(contract, service_rate, settings, actual_billing_start, end_date, proration_factor, total_days)
    else:
        frappe.throw(_("Invalid Billing Basis for contract {0}").format(contract_name))

    # 7. DISCOUNT LOGIC
    # We pass 'contract' and 'settings' as needed by your apply_discount_logic signature
    discount_logic = apply_discount_logic(contract, settings, end_date)
    
    # 8. FINALIZE
    final_breakdown = finalize_breakdown(base_results, discount_logic["total_pct"], discount_logic["selected_rules"])
    
    final_breakdown.update({
        "billing_month": billing_month,
        "billing_year": billing_year,
        "total_days": total_days,
        "actual_start": actual_billing_start
    })
    
    return final_breakdown

def get_active_service_rate(category, reference_date):
    rate_name = frappe.db.get_value("Service Rate", 
        {"service_category": category, "status": "Active", "effective_from": ["<=", reference_date]}, 
        "name", order_by="effective_from desc")
    
    if not rate_name:
        frappe.throw(_("No active Service Rate found for category '{0}' on {1}").format(category, reference_date))
    return frappe.get_doc("Service Rate", rate_name)

def calculate_flat_rate(contract, service_rate, settings, factor, days):
    """Calculates Flat Rate with optional pro-rating."""
    base_price = flt(service_rate.flat_rate_price or 0) * factor
    cistern_fee = (flt(service_rate.cistern_fee or 0) * factor) if contract.has_cistern else 0
    detailed_items = []
    
    # Description suffix for pro-rated bills
    suffix = f" ({days} days)" if factor < 1.0 else ""

    if settings.separate_cistern_fee:
        detailed_items.append({
            "description": _("{0} (Flat Rate - {1})").format(settings.water_service_label,service_rate.rate_name) + suffix,
            "amount": base_price
        })
        if cistern_fee > 0:
            detailed_items.append({"description": _("Cistern Fee") + suffix, "amount": cistern_fee})
    else:
        detailed_items.append({
            "description": _("{0} (Flat Rate)").format(settings.water_service_label) + suffix,
            "amount": base_price + cistern_fee
        })

    category_allows = frappe.db.get_value("Service Category", service_rate.service_category, "allow_discounts")
    discountable_sum = (base_price + cistern_fee) if category_allows else 0
    non_discountable_sum = 0 if category_allows else (base_price + cistern_fee)
    
    for fee in (service_rate.get("additional_fees") or []):
        fee_amt = flt(fee.amount) # Usually additional fees are not pro-rated unless specified
        detailed_items.append({"description": fee.description or _("Additional Fee"), "amount": fee_amt})
        if flt(fee.allow_discounts): discountable_sum += fee_amt
        else: non_discountable_sum += fee_amt
            
    return {
        "discountable_amount": discountable_sum,
        "non_discountable_amount": non_discountable_sum,
        "base_rate": base_price,
        "cistern_fee": cistern_fee,
        "detailed_items": detailed_items
    }

def calculate_metered_rate(contract, service_rate, settings, start_date, end_date, factor, days):
    """Calculates Metered charges using date range for readings."""
    fixed_charge = flt(service_rate.fixed_charge or 0) * factor
    min_m3 = flt(service_rate.min_consumption or 0)
    detailed_items = []
    
    suffix = f" ({days} days)" if factor < 1.0 else ""
    detailed_items.append({
        "description": _("Fixed Charge (Up to {0} m3)").format(min_m3) + suffix,
        "amount": fixed_charge
    })

    # Fetch reading within the specific date range
    reading_data = frappe.db.sql("""
        SELECT consumption FROM `tabMeter Reading` 
        WHERE service_contract = %s AND reading_date BETWEEN %s AND %s AND docstatus = 1
        ORDER BY reading_date DESC LIMIT 1
    """, (contract.name, start_date, end_date), as_dict=True)

    total_consumption = flt(reading_data[0].consumption) if reading_data else 0
    excess_m3 = max(0, total_consumption - min_m3)
    excess_amount = 0.0

    if excess_m3 > 0:
        tiers = service_rate.get("consumption_tiers") or []
        remaining_excess = excess_m3
        prev_limit = min_m3
        for tier in tiers:
            if remaining_excess <= 0: break
            t_limit = flt(tier.up_to_m3)
            t_size = (t_limit - prev_limit) if t_limit > 0 else remaining_excess
            m3_tier = min(remaining_excess, t_size)
            cost = m3_tier * flt(tier.price_per_m3)
            if m3_tier > 0:
                detailed_items.append({
                    "description": _("Excess: {0} m3 at {1}/m3").format(m3_tier, tier.price_per_m3),
                    "amount": cost
                })
                excess_amount += cost
            remaining_excess -= m3_tier
            prev_limit = t_limit

    category_allows = frappe.db.get_value("Service Category", service_rate.service_category, "allow_discounts")
    total_base = fixed_charge + excess_amount
    discountable_sum = total_base if category_allows else 0
    non_discountable_sum = 0 if category_allows else total_base

    return {
        "discountable_amount": discountable_sum,
        "non_discountable_amount": non_discountable_sum,
        "base_rate": fixed_charge,
        "excess_amount": excess_amount,
        "detailed_items": detailed_items
    }

def apply_discount_logic(contract, settings, reference_date):
    subscriber = frappe.get_doc("Subscriber", contract.subscriber)
    if getattr(subscriber, "subscriber_type", "Natural Person") == "Juridical Person":
        return {"total_pct": 0, "selected_rules": []}

    applicable_rules = []
    if subscriber.birth_date:
        age = int(date_diff(reference_date, subscriber.birth_date) / 365.25)
        age_rule = frappe.db.get_value("Discount Rule", 
            {"condition_type": "Age", "minimum_age": ["<=", age], "maximum_age": [">=", age]}, 
            ["name", "discount_percentage"], as_dict=True)
        if not age_rule:
            age_rule = frappe.db.get_value("Discount Rule", 
                {"condition_type": "Age", "minimum_age": ["<=", age], "maximum_age": 0}, 
                ["name", "discount_percentage"], as_dict=True)
        if age_rule: applicable_rules.append(age_rule)

    benefits = frappe.get_all("Benefit Discount",
        filters={"service_contract": contract.name, "status": "Active", "effective_date": ["<=", reference_date]},
        fields=["discount_rule"])
    for b in benefits:
        rule = frappe.db.get_value("Discount Rule", b.discount_rule, ["name", "discount_percentage"], as_dict=True)
        if rule: applicable_rules.append(rule)

    applicable_rules.sort(key=lambda x: flt(x.discount_percentage), reverse=True)
    selected_rules = applicable_rules[:(settings.max_discounts_per_subscriber or 1)]
    total_pct = min(sum(flt(r.discount_percentage) for r in selected_rules), 100.0)
    

    return {"total_pct": total_pct, "selected_rules": selected_rules if total_pct > 0 else []}

def finalize_breakdown(base_results, discount_pct, rules):
    settings = frappe.get_single("Billing Settings")
    
    discountable = base_results["discountable_amount"]
    non_discountable = base_results["non_discountable_amount"]
    
    discount_amount = flt(discountable * (discount_pct / 100))
    
    if settings.truncate_discount_decimals:
        discount_amount = int(discount_amount)
    
    total_to_bill = (discountable + non_discountable) - discount_amount
    
    if settings.truncate_discount_decimals:
        total_to_bill = int(total_to_bill)
        
    items = base_results.get("detailed_items", [])
    
    if discount_amount > 0:
        rule_list = ", ".join([r.name for r in rules])
        items.append({
            "description": _("Applied Discount ({0})").format(rule_list), 
            "amount": -discount_amount
        })
    
    return {
        "total_to_bill": flt(total_to_bill),
        "detailed_items": items,
        "discount_amount": discount_amount,
        "discount_percentage": discount_pct, # El % se queda igual, el monto es el que cambia
        "base_rate": base_results.get("base_rate", 0),
        "cistern_fee": base_results.get("cistern_fee", 0)
    }