# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, date_diff, add_days,get_last_day

def make_debt_ledger_entry(contract_name, entry_type, amount, ref_dt=None, ref_dn=None, description=None):
    """
    PURPOSE: Creates a Debt Ledger Entry in Draft mode, calculating the Due Date 
    based on the specific terms defined in Billing Settings.
    """
    if flt(amount) <= 0:
        frappe.throw(_("Amount must be greater than zero to create a Debt Ledger Entry."))

    # 1. Obtener plazos y configuraciones desde Billing Settings
    settings = frappe.get_doc("Billing Settings")
    
    # 2. Determinar los días de crédito según el tipo de entrada
    if entry_type == "Connection Fee":
        days_to_add = settings.connection_debt_deadline_days or 30
    elif entry_type == "Monthly Fee":
        days_to_add = settings.days_until_due or 15
    else:
        # Para otros cargos usamos el periodo de gracia general
        days_to_add = settings.grace_period or 0

    # 3. Calcular la fecha de vencimiento final
    calculated_due_date = add_days(today(), days_to_add)

    # 4. Crear el objeto del documento (Estado: Draft / docstatus 0)
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
        "status": "Unpaid"
    })
    
    # 5. Insertar en la base de datos
    debt.insert(ignore_permissions=True)
    return debt.name

def allocate_payment_to_debt(receipt_id, debt_id, amount):
    """
    Creates a Payment Allocation record and updates the balances 
    of both the Receipt and the Debt Entry.
    """
    if flt(amount) <= 0: return

    # 1. Create Allocation (The Bridge)
    frappe.get_doc({
        "doctype": "Payment Allocation",
        "payment_receipt": receipt_id,
        "debt_ledger_entry": debt_id,
        "allocated_amount": flt(amount),
        "allocation_date": today()
    }).insert(ignore_permissions=True)

    # 2. Update Debt Entry Balances
    debt = frappe.get_doc("Debt Ledger Entry", debt_id)
    new_paid = flt(debt.paid_amount) + flt(amount)
    
    debt.db_set("paid_amount", new_paid)
    debt.db_set("outstanding_amount", flt(debt.amount) - new_paid)
    
    # Update Status
    new_status = "Paid" if flt(debt.outstanding_amount) <= 0.01 else "Partially Paid"
    debt.db_set("status", new_status)

    # 3. Update Payment Receipt (Reduce its advance credit)
    receipt = frappe.get_doc("Payment Receipt", receipt_id)
    new_unallocated = flt(receipt.unallocated_amount) - flt(amount)
    receipt.db_set("unallocated_amount", new_unallocated)



@frappe.whitelist()
def get_monthly_billing_breakdown(contract_name, billing_month, billing_year):
    """
    Main billing engine. Calculates monthly charges by determining the specific cycle start,
    fetching the correct Service Rate, and resolving complex discount rules.
    """
    contract = frappe.get_doc("Service Contract", contract_name)
    settings = frappe.get_doc("Billing Settings")
    
    # 1. Determinar la fecha de inicio del ciclo (basado en el mes/año seleccionado y el día de inicio)
    cycle_start_date = get_specific_cycle_start(billing_month, billing_year, settings)
    
    # 2. Buscar la tarifa vigente en el maestro 'Service Rate' para esa fecha de inicio
    service_rate = get_active_service_rate(contract.service_category, cycle_start_date)
    
    # 3. Calcular montos base según el Billing Basis del contrato
    if contract.billing_basis == "Flat Rate":
        base_results = calculate_flat_rate(contract, service_rate)
    elif contract.billing_basis == "Metered":
        base_results = calculate_metered_rate(contract, service_rate, settings)
    else:
        frappe.throw(_("Invalid Billing Basis for contract {0}").format(contract_name))

    # 4. Resolver lógica de descuentos (Edad, Beneficios, Stacking, FIFO Priority)
    final_breakdown = apply_discount_logic(contract, settings, base_results, cycle_start_date)
    
    # Añadir metadatos informativos al resultado
    final_breakdown.update({
        "billing_month": billing_month,
        "billing_year": billing_year,
        "cycle_start": cycle_start_date
    })
    
    return final_breakdown

def get_specific_cycle_start(month, year, settings):
    """
    Constructs the specific start date for the billing period. 
    Handles edge cases like day 31 in shorter months.
    """
    start_day = int(settings.cycle_start_day or 1)
    
    try:
        # Intentamos crear la fecha exacta (ej. 2026-01-05)
        cycle_start = getdate(f"{year}-{month}-{start_day}")
    except Exception:
        # Si el día no existe en ese mes, usamos el último día disponible
        first_of_month = getdate(f"{year}-{month}-01")
        cycle_start = get_last_day(first_of_month)

    return cycle_start

def get_active_service_rate(category, reference_date):
    """
    Finds the Service Rate valid at the start of the billing cycle.
    """
    rate_name = frappe.db.get_value("Service Rate", 
        {
            "service_category": category,
            "status": "Active",
            "effective_from": ["<=", reference_date]
        }, 
        "name", 
        order_by="effective_from desc"
    )
    
    if not rate_name:
        frappe.throw(_("No active Service Rate found for category '{0}' effective on {1}")
                     .format(category, reference_date))
        
    return frappe.get_doc("Service Rate", rate_name)

def calculate_flat_rate(contract, service_rate):
    """
    Calculates charges for flat-rate contracts. 
    Base price, cistern fees, and additional fees are all retrieved 
    from the global Service Rate.
    """
    base_price = flt(service_rate.flat_rate_price or 0)
    cistern_fee = flt(service_rate.cistern_fee or 0) if contract.has_cistern else 0
    
    # Fetch category permission for discounts
    category_allows = frappe.db.get_value("Service Category", service_rate.service_category, "allow_discounts")
    
    discountable = 0
    non_discountable = 0
    
    # Base and Cistern logic
    if category_allows:
        discountable = base_price + cistern_fee
    else:
        non_discountable = base_price + cistern_fee
        
    # NEW LOGIC: Fetching additional fees from Service Rate (Global charges)
    # We use .get() on service_rate instead of contract
    global_fees = service_rate.get("additional_fees") or []
    
    for fee in global_fees:
        fee_amount = flt(fee.amount)
        if getattr(fee, "allow_discounts", False):
            discountable += fee_amount
        else:
            non_discountable += fee_amount
            
    return {
        "discountable_amount": discountable,
        "non_discountable_amount": non_discountable,
        "base_rate": base_price,
        "cistern_fee": cistern_fee
    }

def calculate_metered_rate(contract, service_rate, settings):
    """
    Calculates metered charges based on fixed base rate + consumption (placeholder).
    """
    # Cargo fijo por tener medidor (desde Service Rate)
    base_price = flt(service_rate.base_rate or 0)
    
    # TODO: Implementar lógica de rangos de m3 consumidos
    return {
        "discountable_amount": base_price if service_rate.allow_discounts else 0,
        "non_discountable_amount": 0 if service_rate.allow_discounts else base_price,
        "base_rate": base_price,
        "cistern_fee": 0
    }

def apply_discount_logic(contract, settings, base_results, reference_date):
    """
    Resolves complex discount rules: Age ranges, manual benefits, 
    stacking limits, and FIFO contract priority.
    """
    subscriber = frappe.get_doc("Subscriber", contract.subscriber)
    
    # 1. PERSONA JURÍDICA: Las empresas nunca aplican a descuentos
    if getattr(subscriber, "is_company", False):
        return finalize_breakdown(base_results, 0, [])

    applicable_rules = []
    
    # 2. REGLA POR EDAD (Age): Tercera o Cuarta Edad
    if subscriber.birth_date:
        # Edad al momento de iniciar el ciclo de facturación
        age = int(date_diff(reference_date, subscriber.birth_date) / 365.25)
        
        # Buscar regla por rango (min_age / max_age)
        age_rule = frappe.db.get_value("Discount Rule", 
            {
                "condition_type": "Age", 
                "minimum_age": ["<=", age], 
                "maximum_age": [">=", age]
            }, 
            ["name", "discount_percentage"], as_dict=True)
        
        # Si no hay rango cerrado, buscar regla de "X o más" (max = 0)
        if not age_rule:
            age_rule = frappe.db.get_value("Discount Rule", 
                {
                    "condition_type": "Age", 
                    "minimum_age": ["<=", age], 
                    "maximum_age": 0
                }, 
                ["name", "discount_percentage"], as_dict=True)
        
        if age_rule:
            applicable_rules.append(age_rule)

    # 3. BENEFICIOS MANUALES (Benefit Discount)
    benefits = frappe.get_all("Benefit Discount",
        filters={
            "service_contract": contract.name, 
            "status": "Active", 
            "effective_date": ["<=", reference_date]
        },
        fields=["discount_rule"])
    
    for b in benefits:
        rule_data = frappe.db.get_value("Discount Rule", b.discount_rule, ["name", "discount_percentage"], as_dict=True)
        if rule_data:
            applicable_rules.append(rule_data)

    # 4. RESOLUCIÓN DE APILAMIENTO (Stacking)
    # Ordenar de mayor a menor beneficio
    applicable_rules.sort(key=lambda x: flt(x.discount_percentage), reverse=True)
    
    # Tomar N reglas según el límite por abonado en Billing Settings
    max_rules = settings.max_discounts_per_subscriber or 1
    selected_rules = applicable_rules[:max_rules]
    
    # Sumar porcentajes y capar al 100%
    total_pct = sum(flt(r.discount_percentage) for r in selected_rules)
    if total_pct > 100:
        total_pct = 100

    # 5. PRIORIDAD FIFO (Por Contrato)
    # Validar si este contrato califica según el límite de contratos con beneficio
    if total_pct > 0 and settings.max_discounts_per_connection > 0:
        allowed_contracts = frappe.get_all("Service Contract",
            filters={"subscriber": subscriber.name, "status": "Active", "docstatus": 1},
            order_by="creation asc", 
            limit=settings.max_discounts_per_connection, 
            pluck="name")
        
        if contract.name not in allowed_contracts:
            total_pct = 0 # El beneficio no aplica a este contrato (es muy nuevo)

    return finalize_breakdown(base_results, total_pct, selected_rules)

def finalize_breakdown(base_results, discount_pct, rules):
    """
    Executes final mathematics and returns the billable data structure.
    """
    discountable = base_results["discountable_amount"]
    non_discountable = base_results["non_discountable_amount"]
    
    applied_discount_amt = discountable * (discount_pct / 100)
    total_to_bill = (discountable + non_discountable) - applied_discount_amt
    
    return {
        "total_to_bill": flt(total_to_bill),
        "discount_percentage": flt(discount_pct),
        "discount_amount": flt(applied_discount_amt),
        "applied_rules": [r.name for r in rules],
        "base_rate": base_results["base_rate"],
        "cistern_fee": base_results["cistern_fee"],
        "additional_fees": (discountable + non_discountable) - (base_results["base_rate"] + base_results["cistern_fee"])
    }