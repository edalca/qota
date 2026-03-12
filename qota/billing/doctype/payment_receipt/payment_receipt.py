# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    flt,
    today,
    getdate,
    add_months,
    format_date,
    nowdate,
    add_days
)
from datetime import date


class PaymentReceipt(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.payment_receipt_item.payment_receipt_item import PaymentReceiptItem

        amended_from: DF.Link | None
        current_debt: DF.Currency
        edit_posting_date: DF.Check
        full_name: DF.Data | None
        mode_of_payment: DF.Literal["Cash", "Bank Transfer", "Check", "Credit Card"]
        payment_date: DF.Datetime
        payment_items: DF.Table[PaymentReceiptItem]
        premises: DF.Link | None
        reference_no: DF.Data | None
        remarks: DF.SmallText | None
        service_contract: DF.Link
        status: DF.Literal["Draft", "Paid", "Cancelled"]
        subscriber: DF.Link | None
        total_pending: DF.Currency
        total_to_pay: DF.Currency
        unallocated_amount: DF.Currency
    # end: auto-generated types

    def validate(self):
        self.calculate_totals()
        self.status_update()
        self.validate_payment_sequence()

    def validate_payment_sequence(self):
        """
        Ensures that no billing periods are skipped.
        All unpaid debts must be included if an advance is present,
        and selected months must be sequential.
        """
        from frappe.utils import add_months

        selected_items = [
            d for d in self.payment_items if (
                d.payment_concept == "Monthly Fee"
            )
        ]

        if not selected_items:
            return

        def parse_period(p_str):
            parts = p_str.split('-')
            return date(int(parts[1]), int(parts[0]), 1)

        selected_items.sort(key=lambda x: parse_period(x.billing_period))

        oldest_pending_debt = frappe.db.get_value("Debt Ledger Entry", {
            "service_contract": self.service_contract,
            "entry_type": "Monthly Fee",
            "outstanding_amount": [">", 0],
            "docstatus": ["!=", 2]
        }, "billing_period", order_by="due_date asc")

        if oldest_pending_debt:
            first_selected = selected_items[0].billing_period
            if (
                parse_period(first_selected) >
                parse_period(oldest_pending_debt)
            ):
                frappe.throw(
                    _(
                        "You cannot skip pending debts. Please include {0} "
                        "before adding future months.")
                    .format(frappe.bold(oldest_pending_debt))
                )

        for i in range(len(selected_items) - 1):
            curr_date = parse_period(selected_items[i].billing_period)
            next_date = parse_period(selected_items[i+1].billing_period)

            if next_date != add_months(curr_date, 1):
                frappe.throw(
                    _(
                        "Sequence error: There is a gap between {0} and {1}. "
                        "Payments must be sequential.")
                    .format(frappe.bold(selected_items[i].billing_period),
                            frappe.bold(selected_items[i+1].billing_period))
                )

    def before_submit(self):
        for item in self.payment_items:
            # Al inicio, el saldo disponible es el total del item
            item.balance = item.amount

    def on_submit(self):
        """
        Al confirmar el recibo, actualizamos el saldo de las deudas vinculadas.
        """
        self.process_ledger_updates(cancel=False)

    def on_cancel(self):
        """
        Al cancelar el recibo, devolvemos el saldo a las deudas.
        """
        self.process_ledger_updates(cancel=True)

    def status_update(self):
        if self.docstatus == 0:
            self.status = "Draft"
        elif self.docstatus == 1:
            self.status = "Paid"
        elif self.docstatus == 2:
            self.status = "Cancelled"

    def process_ledger_updates(self, cancel=False):
        for item in self.payment_items:
            if not cancel and flt(item.balance) == 0:
                item.balance = item.amount

            if item.debt_ledger_entry:
                debt = frappe.get_doc("Debt Ledger Entry",
                                      item.debt_ledger_entry)

                amount_to_apply = (
                    min(flt(item.balance),
                        flt(debt.outstanding_amount))
                )

                if cancel:
                    applied_in_this_item = flt(item.amount) - flt(item.balance)
                    debt.outstanding_amount += applied_in_this_item
                    debt.paid_amount -= applied_in_this_item
                    item.balance = item.amount
                else:
                    if amount_to_apply <= 0:
                        continue

                    debt.outstanding_amount -= amount_to_apply
                    debt.paid_amount += amount_to_apply

                    item.balance = flt(item.balance) - amount_to_apply

                # --- Gestión de Estados de la Deuda ---
                if flt(debt.outstanding_amount) <= 0.01:
                    debt.status = "Paid"
                elif flt(debt.paid_amount) > 0:
                    debt.status = "Partially Paid"
                else:
                    debt.status = "Unpaid"

                # Guardar cambios en la Deuda
                debt.flags.ignore_validate_update_after_submit = True
                debt.save(ignore_permissions=True)

                # Guardar el nuevo balance en el ítem del recibo
                item.db_set("balance", item.balance)

    def calculate_totals(self):
        total_to_pay = 0.0
        unallocated_amount = 0.0

        # Recorremos la única tabla: payment_items
        if self.get("payment_items"):
            for item in self.payment_items:
                # Sumar al total pagado
                total_to_pay += flt(item.amount)

                # Si NO tiene debt_ledger_entry, es un adelanto (unallocated)
                if not item.debt_ledger_entry:
                    unallocated_amount += flt(item.amount)

        self.total_to_pay = total_to_pay
        self.unallocated_amount = unallocated_amount

        self.total_pending = (
            flt(self.current_debt) - total_to_pay
            + unallocated_amount
        )

    @frappe.whitelist()
    @staticmethod
    def get_next_billing_advances(
        self,
        contract_name,
        qty=12,
        ignore_existing=False
    ):
        """
        Calculate billing periods for advances or full cycle (Talonario).
        """
        from qota.billing.utils import get_monthly_billing_breakdown

        contract = frappe.get_doc("Service Contract", contract_name)
        settings = frappe.get_single("Billing Settings")
        start_day = int(settings.cycle_start_day or 1)

        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        contract_start = getdate(contract.start_date)
        reactivation_dt = (getdate(contract.reactivation_date)
                           if contract.reactivation_date else None)
        effective_start_date = (reactivation_dt
                                if reactivation_dt and
                                reactivation_dt > contract_start
                                else contract_start)

        existing_periods = set()
        if not ignore_existing:
            debts = frappe.get_all("Debt Ledger Entry", filters={
                "service_contract": contract_name,
                "entry_type": "Monthly Fee",
                "docstatus": ["!=", 2]
            }, pluck="billing_period")
            existing_periods.update(debts)

            paid = frappe.db.sql("""
                SELECT pri.billing_period
                FROM `tabPayment Receipt Item` pri
                JOIN `tabPayment Receipt` pr ON pri.parent = pr.name
                WHERE pr.service_contract = %s
                AND pri.payment_concept = 'Monthly Fee'
                AND pr.docstatus = 1 AND pri.billing_period IS NOT NULL
            """, (contract_name,), as_dict=True)
            for pa in paid:
                existing_periods.add(pa.billing_period)

        # 3. Mapa de Años Fiscales Abiertos
        open_years = frappe.get_all(
            "Billing Year",
            filters={"is_closed": 0},
            fields=["name", "year_name"]
        )
        open_years_map = {int(y.year_name): y.name for y in open_years}

        if not open_years_map:
            return []

        min_year = min(open_years_map.keys())
        if ignore_existing:
            current_date = date(min_year, 1, 1)
        else:
            start_year = max(effective_start_date.year, min_year)
            current_date = date(start_year, effective_start_date.month, 1)

        advances = []
        today_date = nowdate()
        iterations = 0

        while len(advances) < int(qty) and iterations < (int(qty) * 2):
            iterations += 1
            y_num = current_date.year
            m_num = current_date.month
            period_id = current_date.strftime("%m-%Y")

            fiscal_year_link = open_years_map.get(y_num)
            if not fiscal_year_link:
                current_date = add_months(current_date, 1)
                continue

            if ignore_existing or (period_id not in existing_periods):
                month_str = month_names[m_num - 1]
                p_start = date(y_num, m_num, start_day)
                p_end = add_days(add_months(p_start, 1), -1)

                breakdown = get_monthly_billing_breakdown(
                    contract_name=contract_name,
                    billing_month=month_str,
                    billing_year=fiscal_year_link,
                    start_date=p_start,
                    end_date=p_end
                )

                advances.append({
                    "billing_period": period_id,
                    "month_num": m_num,
                    "month_label": f"{_(month_str)} {y_num}",
                    "year": y_num,
                    "due_date": today_date,
                    "amount": flt(breakdown.get("total_to_bill", 0)),
                    "discount_amount":
                    flt(breakdown.get("discount_amount", 0)),
                    "description": _("Advance Payment: {0}").format(
                        format_date(current_date, 'MMMM YYYY')),
                    "billing_details": breakdown.get("detailed_items", [])
                })

            current_date = add_months(current_date, 1)

        return advances


@frappe.whitelist()
def get_pending_balances(contract):
    """
    Fetches existing debts and determines mandatory status based on due dates.
    """
    debts = frappe.get_all(
        "Debt Ledger Entry",
        filters={
            "service_contract": contract,
            "outstanding_amount": [">", 0],
            "docstatus": ["!=", 2]
        },
        fields=["name as debt_id",
                "entry_type as payment_concept",
                "outstanding_amount as amount",
                "due_date",
                "description",
                "billing_period"],
        order_by="creation asc"
    )

    current_date = getdate(today())
    for d in debts:
        # Una deuda es obligatoria si ya pasó su fecha de vencimiento
        d['days_diff'] = (
            frappe.utils.date_diff(d['due_date'], current_date)
            if d['due_date'] else 0
        )

    return {
        "debts": debts,
        "current_debt": sum(flt(d['amount']) for d in debts)
    }
