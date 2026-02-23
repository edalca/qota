# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import random
import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)

    return columns, data, None, chart


def get_columns():
    return [
        {"label": _("Subscriber"), "fieldname": "subscriber",
         "fieldtype": "Data", "width": 180},
        {"label": _("Service Contract"), "fieldname": "contract",
         "fieldtype": "Link", "options": "Service Contract", "width": 120},
        {"label": _("Block"), "fieldname": "block",
         "fieldtype": "Data", "width": 100},
        {"label": _("House Number"), "fieldname": "house_number",
         "fieldtype": "Data", "width": 100},
        {"label": _("Advance Amount"), "fieldname": "advance_amount",
         "fieldtype": "Currency", "width": 130}
    ]


def get_data(filters):
    # Condiciones base para pagos adelantados
    conditions = (
        "(pri.debt_ledger_entry IS NULL OR pri.debt_ledger_entry = '') "
        "AND pr.docstatus = 1 "
    )

    # Filtros dinámicos
    if filters.get("service_contract"):
        conditions += " AND pr.service_contract = %(service_contract)s"

    if filters.get("block"):
        conditions += " AND p.block = %(block)s"

    if filters.get("house_number"):
        conditions += " AND p.house_number = %(house_number)s"

    # SQL con el JOIN hacia tabPremises (alias 'p')
    return frappe.db.sql(f"""
        SELECT
            pr.full_name as subscriber,
            pr.service_contract as contract,
            p.block as block,
            p.house_number as house_number,
            pri.amount as advance_amount
        FROM
            `tabPayment Receipt Item` pri
        INNER JOIN
            `tabPayment Receipt` pr ON pri.parent = pr.name
        LEFT JOIN
            `tabService Contract` sc ON pr.service_contract = sc.name
        LEFT JOIN
            `tabPremises` p ON sc.premises = p.name
        WHERE
            {conditions}
        ORDER BY
            p.block ASC, p.house_number ASC
    """, filters, as_dict=1)


def get_chart(data):
    if not data:
        return None

    warm_colors = [
        "#E67E22",  # Naranja Zanahoria
        "#5DADE2",  # Azul Cielo Intenso
        "#48C9B0",  # Turquesa Medio
        "#F4D03F",  # Amarillo Girasol
        "#EB984E",  # Bronce Suave
        "#AF7AC5",  # Púrpura Amatista
        "#52BE80",  # Verde Selva
        "#EC7063",  # Coral Fuerte
        "#5499C7",  # Azul Océano
        "#A569BD"   # Violeta Medio
    ]

    block_summary = {}
    for row in data:
        block = row.get("block") or _("Unknown")
        amount = row.get("advance_amount") or 0
        block_summary[block] = block_summary.get(block, 0) + amount

    labels = sorted(block_summary.keys())
    values = [block_summary[k] for k in labels]

    selected_color = random.choice(warm_colors)

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "name": _("Advance Amount"),
                    "values": values
                }
            ]
        },
        "type": "bar",
        "colors": [selected_color],
        "barOptions": {
            "spaceRatio": 0.5
        }
    }
