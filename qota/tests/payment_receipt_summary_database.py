"""Receipt lifecycle and accounting summaries on the local database."""

import os
from calendar import month_name, monthrange
from contextlib import ExitStack
from datetime import date, timedelta
import unittest
from unittest.mock import patch

import frappe

from qota.billing.doctype.payment_receipt.payment_receipt import get_pending_balances


class PaymentReceiptSummaryTests(unittest.TestCase):
    def setUp(self):
        frappe.set_user('Administrator')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.addCleanup(frappe.db.rollback)
        self.stack.enter_context(patch.object(frappe.db, 'commit', lambda: None))
        self.subscriber = self.insert('Subscriber', full_name='Ana Example', primary_phone='91234567',
            primary_phone_region='HN', primary_phone_national='91234567', primary_phone_e164='+50491234567')
        self.contract = 'SC-99999'
        frappe.get_doc(dict(doctype='Service Contract', name=self.contract, docstatus=1,
            subscriber=self.subscriber, status='Active', start_date='2026-01-01')).db_insert()
        self.year = '2026' if frappe.db.exists('Billing Year', '2026') else self.insert('Billing Year', name='2026', year_name='2026')
        original_single = frappe.get_single
        self.stack.enter_context(patch.object(frappe, 'get_single', side_effect=lambda dt:
            frappe._dict(default_currency='HNL') if dt == 'Billing Settings' else original_single(dt)))

    def insert(self, doctype, **values):
        import uuid
        name = values.pop('name', f'RECEIPT-TEST-{uuid.uuid4().hex[:8]}')
        doc = frappe.get_doc(dict(doctype=doctype, name=name, **values))
        doc.db_insert()
        return doc.name

    def debt(self, period, amount=160):
        month, year = map(int, period.split('-'))
        start, end = date(year, month, 1), date(year, month, monthrange(year, month)[1])
        bill = self.insert('Monthly Bill', service_contract=self.contract, docstatus=1,
            grand_total=amount, fiscal_month=month_name[month], fiscal_year=self.year,
            start_date=start, end_date=end, posting_date=start, status='Unpaid')
        return self.insert('Debt Ledger Entry', service_contract=self.contract, entry_type='Monthly Fee',
            billing_period=period, due_date=end + timedelta(days=1), amount=amount, outstanding_amount=amount,
            paid_amount=0, status='Unpaid', reference_doctype='Monthly Bill', reference_name=bill)

    def create_receipt(self, items, **values):
        doc = frappe.get_doc(dict(doctype='Payment Receipt', service_contract=self.contract,
            subscriber=self.subscriber, full_name='Ana Example', payment_date='2026-10-16',
            mode_of_payment='Cash', payment_items=items, **values))
        # Synthetic contracts omit unrelated linked premises fixtures.
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        return doc

    def item(self, debt, period, amount):
        return dict(payment_concept='Monthly Fee', debt_ledger_entry=debt, billing_period=period, amount=amount)

    def assert_accounting(self, doc, before, after, outstanding):
        self.assertEqual((doc.current_debt, doc.total_pending), (before, after))
        doc.submit(); doc.reload()
        self.assertEqual((doc.current_debt, doc.total_pending), (before, after))
        self.assertEqual(get_pending_balances(self.contract)['current_debt'], after)
        for debt, paid, pending in outstanding:
            row = frappe.get_doc('Debt Ledger Entry', debt)
            self.assertEqual((row.paid_amount, row.outstanding_amount), (paid, pending))
        self.assertEqual(frappe.db.get_value('Service Contract', self.contract, 'status'), 'Active')
        self.assertEqual(sum(i.amount - i.balance for i in doc.payment_items), before - after)

    def test_backend_full_payment_multiple_periods_without_browser_totals(self):
        first, second = self.debt('08-2026'), self.debt('09-2026')
        doc = self.create_receipt([self.item(first, '08-2026', 160), self.item(second, '09-2026', 160)])
        self.assert_accounting(doc, 320, 0, [(first, 160, 0), (second, 160, 0)])

    def test_form_values_are_verified_and_stale_values_cannot_override_ledger(self):
        debt = self.debt('08-2026')
        form_debt = get_pending_balances(self.contract)['current_debt']
        doc = self.create_receipt([self.item(debt, '08-2026', 60)], current_debt=form_debt, total_pending=100)
        self.assertEqual((doc.current_debt, doc.total_pending), (160, 100))
        doc.current_debt = 9999; doc.total_pending = -9999; doc.save()
        self.assert_accounting(doc, 160, 100, [(debt, 60, 100)])

    def test_submit_refreshes_draft_snapshot_after_another_payment(self):
        debt = self.debt('08-2026')
        draft = self.create_receipt([self.item(debt, '08-2026', 60)])
        other = self.create_receipt([self.item(debt, '08-2026', 40)])
        other.submit()
        draft.submit(); draft.reload()
        self.assertEqual((draft.current_debt, draft.total_pending), (120, 60))
        self.assertEqual(get_pending_balances(self.contract)['current_debt'], 60)

    def test_monthly_period_fallback_is_included_before_submit(self):
        debt = self.debt('08-2026')
        doc = self.create_receipt([self.item(None, '08-2026', 100)])
        self.assertEqual(doc.payment_items[0].debt_ledger_entry, debt)
        self.assert_accounting(doc, 160, 60, [(debt, 100, 60)])

    def test_advance_without_debt_does_not_create_negative_pending(self):
        doc = self.create_receipt([self.item(None, '11-2026', 160)])
        self.assert_accounting(doc, 0, 0, [])
        self.assertEqual((doc.payment_items[0].balance, doc.unallocated_amount), (160, 160))
        debt = self.debt('11-2026')
        # Exercise the existing ledger lifecycle which consumes the saved advance.
        frappe.get_doc('Debt Ledger Entry', debt).apply_advance_payments()
        doc.reload()
        self.assertEqual(doc.payment_items[0].balance, 0)
        self.assertEqual(get_pending_balances(self.contract)['current_debt'], 0)
        self.assertEqual((doc.current_debt, doc.total_pending), (0, 0))

    def test_mixed_debt_and_future_advance(self):
        debt = self.debt('10-2026')
        doc = self.create_receipt([self.item(debt, '10-2026', 160), self.item(None, '11-2026', 160)])
        self.assert_accounting(doc, 160, 0, [(debt, 160, 0)])
        self.assertEqual((doc.total_to_pay, doc.unallocated_amount), (320, 160))

    def test_repeated_items_and_surplus_only_project_actual_applications(self):
        debt = self.insert('Debt Ledger Entry', service_contract=self.contract, entry_type='Other Fee',
            due_date='2026-10-01', amount=160, outstanding_amount=160, paid_amount=0, status='Unpaid')
        items = [dict(payment_concept='Other Fee', debt_ledger_entry=debt, amount=100) for _ in range(2)]
        doc = self.create_receipt(items, current_debt=0)
        self.assert_accounting(doc, 160, 0, [(debt, 160, 0)])
        self.assertEqual(sum(i.balance for i in doc.payment_items), 40)


def main():
    frappe.init(site='qota.localhost', sites_path='/home/frappe/frappe-bench/sites')
    os.chdir('/home/frappe/frappe-bench/sites'); frappe.connect(); frappe.set_user('Administrator')
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(PaymentReceiptSummaryTests))
        return 0 if result.wasSuccessful() else 1
    finally:
        frappe.db.rollback(); frappe.destroy()


if __name__ == '__main__':
    raise SystemExit(main())
