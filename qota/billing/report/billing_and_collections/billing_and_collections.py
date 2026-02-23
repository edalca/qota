# Copyright (c) 2026, Edwin Carrillo y colaboradores
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Period"),
         "fieldname": "period",
         "fieldtype": "Data",
         "width": 100},
        {"label": _("Billed Amount"),
         "fieldname": "billed",
         "fieldtype": "Currency",
         "width": 120},
        {"label": _("Regular Payments"),
         "fieldname": "regular_paid",
         "fieldtype": "Currency",
         "width": 130},
        {"label": _("Applied Advances"),
         "fieldname": "advances_paid",
         "fieldtype": "Currency",
         "width": 130},
        {"label": _("Total Collected"),
         "fieldname": "total_collected",
         "fieldtype": "Currency",
         "width": 130},
        {"label": _("Pending Balance"),
         "fieldname": "pending",
         "fieldtype": "Currency",
         "width": 130},
        {"label": _("Efficiency %"),
         "fieldname": "efficiency",
         "fieldtype": "Percent",
         "width": 100}
    ]


def get_data(filters):
    """
    Retrieves and aggregates billing and collection data.

    Fetches debt entries and receipts based on filters, calculating
    billed amounts and efficiency. Advances are identified if paid
    before the debt ledger entry was created.

    Args:
        filters (dict): Report filters (e.g., fiscal_year).

    Returns:
        list: Chronologically sorted list of metrics per period.
    """
    dle_conditions = ""
    if filters.get("fiscal_year"):
        dle_conditions = " WHERE YEAR(creation) = %(fiscal_year)s"

    ledgers = frappe.db.sql(f"""
        SELECT
            name, billing_period, amount, paid_amount,
            outstanding_amount, creation
        FROM `tabDebt Ledger Entry`
        {dle_conditions}
    """, filters, as_dict=1)

    pay_conditions = (
        "WHERE pr.docstatus = 1"
    )

    if filters.get("fiscal_year"):
        pay_conditions += " AND YEAR(payment_date) = %(fiscal_year)s"

    payments = frappe.db.sql(f"""
        SELECT
            pri.amount, pri.debt_ledger_entry,
            pr.payment_date, pri.billing_period
        FROM `tabPayment Receipt Item` pri
        INNER JOIN `tabPayment Receipt` pr ON pri.parent = pr.name
        {pay_conditions}
    """, filters, as_dict=1)

    report_map = {}

    for dle in ledgers:
        period = dle.billing_period
        if period not in report_map:
            report_map[period] = create_empty_period(period)

        report_map[period]["billed"] += dle.amount
        report_map[period]["ledger_dates"][dle.name] = dle.creation

    for pay in payments:
        period = pay.billing_period
        if period not in report_map:
            report_map[period] = create_empty_period(period)

        row = report_map[period]
        dle_creation = row["ledger_dates"].get(pay.debt_ledger_entry)

        # Logical separation for advance payment detection
        is_advance = not pay.debt_ledger_entry or (
            dle_creation and pay.payment_date < dle_creation
        )

        if is_advance:
            row["advances_paid"] += pay.amount
        else:
            row["regular_paid"] += pay.amount

        row["total_collected"] += pay.amount

    # Sorting logic: Ascending by Year then Month
    sorted_periods = sorted(
        report_map.keys(),
        key=lambda x: (x.split('-')[1], x.split('-')[0])
    )

    final_data = []
    for p in sorted_periods:
        row = report_map[p]
        row["pending"] = max(0, row["billed"] - row["total_collected"])

        if row["billed"] > 0:
            row["efficiency"] = (row["total_collected"] / row["billed"]) * 100
        elif row["total_collected"] > 0:
            row["efficiency"] = 100

        mm, yyyy = p.split('-')
        row["period"] = f"{yyyy}-{mm}"
        row.pop("ledger_dates")
        final_data.append(row)

    return final_data


def create_empty_period(period):
    """Estructura base para un nuevo periodo en el mapa."""
    return {
        "period": period,
        "billed": 0.0,
        "regular_paid": 0.0,
        "advances_paid": 0.0,
        "total_collected": 0.0,
        "pending": 0.0,
        "efficiency": 0.0,
        "ledger_dates": {}
    }
