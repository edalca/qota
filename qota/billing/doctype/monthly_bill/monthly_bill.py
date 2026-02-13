# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate,add_days

class MonthlyBill(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.monthly_bill_item.monthly_bill_item import MonthlyBillItem

        amended_from: DF.Link | None
        billing_cycle: DF.Link | None
        billing_details_json: DF.SmallText | None
        edit_posting_date: DF.Check
        end_date: DF.Date | None
        fiscal_month: DF.Literal["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        fiscal_year: DF.Link
        full_name: DF.Data | None
        grand_total: DF.Currency
        items: DF.Table[MonthlyBillItem]
        posting_date: DF.Date
        premises: DF.Link | None
        service_contract: DF.Link
        start_date: DF.Date | None
        status: DF.Literal["Draft", "Submitted", "Cancelled", "Paid"]
    # end: auto-generated types

    def validate(self):
        self.validate_dates()
        self.check_duplicate_fiscal_period()
        self.check_duplicate_period()
        self.validate_sequence()
        self.calculate_breakdown()

    def check_duplicate_fiscal_period(self):
        """
        Prevents multiple bills for the same fiscal month and year
        even if dates are slightly different.
        """
        duplicate = frappe.db.exists("Monthly Bill", {
            "service_contract": self.service_contract,
            "fiscal_year": self.fiscal_year,
            "fiscal_month": self.fiscal_month,
            "name": ["!=", self.name],
            "docstatus": ["!=", 2] # Ignore cancelled bills
        })

        if duplicate:
            frappe.throw(_("A Monthly Bill already exists for this contract in {0} {1} (Reference: {2})").format(
                self.fiscal_month, self.fiscal_year, duplicate
            ))

    def validate_dates(self):
        """Ensures service dates are present and logically ordered"""
        if not self.start_date or not self.end_date:
            frappe.throw(_("Service Start Date and End Date are required."))
        
        if getdate(self.start_date) >= getdate(self.end_date):
            frappe.throw(_("Service End Date must be after Service Start Date."))

    def check_duplicate_period(self):
        """
        Prevents overlapping service periods (collision detection).
        """
        overlapping_bill = frappe.db.sql("""
            SELECT name FROM `tabMonthly Bill`
            WHERE service_contract = %s
              AND name != %s
              AND docstatus != 2
              AND (
                (%s BETWEEN start_date AND end_date) OR
                (%s BETWEEN start_date AND end_date) OR
                (start_date BETWEEN %s AND %s)
              )
            LIMIT 1
        """, (self.service_contract, self.name, self.start_date, self.end_date, self.start_date, self.end_date))

        if overlapping_bill:
            frappe.throw(_("The selected date range overlaps with an existing Monthly Bill: {0}").format(
                overlapping_bill[0][0]
            ))

    def validate_sequence(self,throw_error=True):
        """
        Ensures fiscal continuity. Checks that the previous month has a bill
        before allowing the current one, starting from the contract's start 
        or the oldest open fiscal year.
        """
        # 1. Setup month mapping
        month_map = {
            "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
            "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12
        }
        rev_month_map = {v: k for k, v in month_map.items()}
        
        # 2. Get current bill period info
        curr_month_val = month_map.get(self.fiscal_month)
        curr_year_str = frappe.db.get_value("Billing Year", self.fiscal_year, "year_name")
        if not curr_year_str: return
        
        curr_year_val = int(curr_year_str)
        # Unique index for the current period: (Year * 12) + Month
        curr_idx = (curr_year_val * 12) + curr_month_val

        # 3. Get Contract start period
        c_start_date = frappe.db.get_value("Service Contract", self.service_contract, "start_date")
        if not c_start_date: return
        c_dt = getdate(c_start_date)
        c_idx = (c_dt.year * 12) + c_dt.month

        # 4. Get Oldest Open Year period
        # We only care about gaps in years that are still manageable (is_closed=0)
        oldest_open_year = frappe.db.get_value("Billing Year", {"is_closed": 0}, "year_name", order_by="year_name asc")
        if not oldest_open_year: return
        o_idx = (int(oldest_open_year) * 12) + 1

        # 5. Determine the 'Strict Start': The first month this contract MUST be billed
        # It's the later of: The day the contract started OR the start of the oldest open year
        required_start_idx = max(c_idx, o_idx)

        # 6. Validation Logic
        if curr_idx < required_start_idx:
            # User is trying to bill a month before the contract started or a closed year
            frappe.throw(_("Invalid Period: Contract starts on {0}. First billable period is {1} {2}.").format(
                frappe.format_date(c_start_date), 
                _(rev_month_map[required_start_idx % 12 or 12]), 
                (required_start_idx - 1) // 12
            ))

        if curr_idx > required_start_idx:
            # This is not the first bill; we must verify the PREVIOUS month exists
            prev_idx = curr_idx - 1
            prev_month_num = prev_idx % 12 or 12
            prev_year_num = (prev_idx - 1) // 12
            
            # Get the Billing Year document name for the previous year
            prev_year_link = frappe.db.get_value("Billing Year", {"year_name": str(prev_year_num)}, "name")
            
            if prev_year_link:
                # Check if previous month has a submitted or draft bill
                exists = frappe.db.exists("Monthly Bill", {
                    "service_contract": self.service_contract,
                    "fiscal_year": prev_year_link,
                    "fiscal_month": rev_month_map[prev_month_num],
                    "docstatus": ["!=", 2]
                })

                if not exists:
                    error_msg = _("Billing Continuity Error: Missing bill for {0} {1}.").format(
                        _(rev_month_map[prev_month_num]), prev_year_num
                    )
                    
                    if throw_error:
                        frappe.throw(error_msg)
                    return error_msg 
                return None

    def calculate_breakdown(self):
        """Passes coverage dates to the engine, which will cross-check with Contract Start"""
        if not self.items and self.start_date and self.end_date:
            from qota.billing.utils import get_monthly_billing_breakdown
            
            # Pricing engine handles the logic of contract.start_date vs self.start_date
            breakdown = get_monthly_billing_breakdown(
                contract_name=self.service_contract,
                billing_month=self.fiscal_month,
                billing_year=self.fiscal_year,
                start_date=self.start_date,
                end_date=self.end_date
            )
            
            self.items = []
            for item in breakdown.get("detailed_items", []):
                self.append("items", {
                    "description": item["description"],
                    "amount": item["amount"]
                })
            
            self.grand_total = flt(breakdown.get("total_to_bill"))

    def on_submit(self):
        self.create_debt_entry()
        self.apply_advance_payments()
        self.prepare_audit_json()

    def on_cancel(self):
        """Cleanup: Locate debt by reference and remove if unpaid"""
        debt_name = frappe.db.get_value("Debt Ledger Entry", {
            "reference_doctype": "Monthly Bill",
            "reference_name": self.name
        }, "name")

        if debt_name:
            paid_amount = frappe.db.get_value("Debt Ledger Entry", debt_name, "paid_amount")
            
            if flt(paid_amount) > 0:
                # Using frappe.format_value directly
                formatted_paid = frappe.format_value(paid_amount, {"fieldtype": "Currency"})
                frappe.throw(_("Cannot cancel bill {0} because the associated debt has recorded payments ({1}).").format(
                    self.name, formatted_paid
                ))

            frappe.db.sql("""
                UPDATE `tabPayment Receipt Item`
                SET debt_ledger_entry = NULL
                WHERE debt_ledger_entry = %s
            """, debt_name)

            frappe.delete_doc("Debt Ledger Entry", debt_name, force=1)

        self.db_set("status", "Cancelled")

    def create_debt_entry(self):
        from qota.billing.utils import make_debt_ledger_entry
        
        year_val = frappe.db.get_value("Billing Year", self.fiscal_year, "year_name")
        month_map = {
            "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
            "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12
        }

        make_debt_ledger_entry(
            contract_name=self.service_contract,
            entry_type="Monthly Fee",
            amount=self.grand_total,
            ref_dt="Monthly Bill",
            ref_dn=self.name,
            description=_("Monthly Fee: {0} {1}").format(self.fiscal_month, year_val),
            fiscal_month=month_map.get(self.fiscal_month), 
            fiscal_year=int(year_val)
        )

    def apply_advance_payments(self):
        """Matches advance payments using the new balance field"""
        debt_name = frappe.db.get_value("Debt Ledger Entry", {
            "reference_doctype": "Monthly Bill", 
            "reference_name": self.name
        }, "name")

        if not debt_name: return

        # ... (tu mapeo de meses y target_period igual) ...
        year_val = frappe.db.get_value("Billing Year", self.fiscal_year, "year_name")
        month_map = {"January":"01","February":"02","March":"03","April":"04","May":"05","June":"06",
                     "July":"07","August":"08","September":"09","October":"10","November":"11","December":"12"}
        target_period = f"{month_map[self.fiscal_month]}-{year_val}"

        # CAMBIO: Buscamos ítems que tengan BALANCE > 0
        advance = frappe.db.sql("""
            SELECT item.name, item.balance, item.amount 
            FROM `tabPayment Receipt Item` item
            INNER JOIN `tabPayment Receipt` parent ON parent.name = item.parent
            WHERE parent.service_contract = %s 
              AND item.billing_period = %s 
              AND parent.docstatus = 1 
              AND item.balance > 0
            LIMIT 1
        """, (self.service_contract, target_period), as_dict=True)

        if advance:
            adv_item = advance[0]
            debt = frappe.get_doc("Debt Ledger Entry", debt_name)
            
            # Usamos el balance, no el amount total
            available_money = flt(adv_item.balance)
            needed_money = flt(debt.amount)

            amount_to_apply = min(available_money, needed_money)

            # 1. Actualizar la Deuda
            debt.paid_amount = amount_to_apply
            debt.outstanding_amount = needed_money - amount_to_apply
            debt.status = "Paid" if debt.outstanding_amount <= 0.01 else "Partially Paid"
            debt.save(ignore_permissions=True)
            
            # 2. Actualizar el SOBRANTE en el Recibo
            new_balance = available_money - amount_to_apply
            frappe.db.set_value("Payment Receipt Item", adv_item.name, {
                "balance": new_balance,
                "debt_ledger_entry": debt_name # Mantenemos el link por referencia
            })


    def prepare_audit_json(self):
        details = [{"description": i.description, "amount": i.amount} for i in self.items]
        self.db_set("billing_details_json", json.dumps(details))