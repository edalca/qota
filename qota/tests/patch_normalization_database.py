"""Historical migrations and navigation setup on a MariaDB site with transaction rollback."""

from contextlib import ExitStack
import importlib
import os
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import frappe
from frappe.modules.patch_handler import PatchError
from qota import setup
from qota.tests.patch_normalization import RELEASE_16_10_0_PATCHES

PREFIX = 'qota.patches.'


def migration(name):
    version = 'v16_10_0' if name in RELEASE_16_10_0_PATCHES else 'v16_9_0'
    return importlib.import_module(f'{PREFIX}{version}_{name}')


class MigrationDatabaseTests(unittest.TestCase):
    def setUp(self):
        frappe.set_user('Administrator')
        frappe.db.rollback()
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(frappe.db, 'commit', lambda: None))
        self.addCleanup(self.stack.close)
        self.addCleanup(frappe.db.rollback)
        self.prefix = 'PATCH-TEST-' + uuid.uuid4().hex[:10]
        self.early = datetime(2026,1,1)
        self.cutoff = self.early + timedelta(days=5)
        self.contract = self.prefix + '-contract'

    def insert(self, dt, **fields):
        values=dict(doctype=dt,name=self.prefix+'-'+uuid.uuid4().hex[:8],creation=self.early,modified=self.early)
        values.update(fields)
        doc = frappe.get_doc(values)
        doc.db_insert()
        return doc.name

    def body(self, name):
        # Identity guards are independently covered; use the body without log edits.
        migration(name)._migrate()

    def debt(self, **fields):
        defaults=dict(service_contract=self.contract,entry_type='Monthly Fee',billing_period='01-2026',
            amount=100,paid_amount=100,outstanding_amount=0,status='Paid',docstatus=1)
        defaults.update(fields)
        return self.insert('Debt Ledger Entry',**defaults)

    def refinancing(self, total=100):
        ref=self.insert('Debt Refinancing',docstatus=1,service_contract=self.contract,current_total_debt=total)
        self.debt(entry_type='Refinancing Installment',amount=total,paid_amount=0,outstanding_amount=total,
            status='Unpaid',reference_doctype='Debt Refinancing',reference_name=ref,creation=self.cutoff)
        return ref

    def test_navigation_additive_operator_preferences_and_no_source_export(self):
        dock=frappe.get_doc('Dock','qota')
        dock.append('items',dict(added=1,icon='settings',link_type='Sidebar',link_to='Billing',title='Custom title',hidden=1))
        for row in dock.items:
            if row.link_to=='Subscribers':row.title='Subscribers'
        setup._save_navigation(dock)
        sidebar=frappe.get_doc('Sidebar','Subscribers')
        sidebar.items=[r for r in sidebar.items if r.link_to!='Institutional Settings']
        sidebar.append('items',dict(type='Link',link_type='DocType',link_to='Subscriber',label='Custom link'))
        setup._save_navigation(sidebar)
        previous=frappe.flags.in_import
        setup.ensure_navigation();setup.ensure_navigation()
        self.assertEqual(frappe.flags.in_import,previous)
        dock=frappe.get_doc('Dock','qota')
        sub_row=next(r for r in dock.items if r.link_to=='Subscribers')
        self.assertEqual(sub_row.title,'Governance')
        self.assertTrue(any(r.title=='Custom title' and r.hidden==1 for r in dock.items))
        self.assertFalse(any(r.link_to in ('Conversations','Communications') for r in dock.items))
        sidebar=frappe.get_doc('Sidebar','Subscribers')
        self.assertEqual(sum(r.link_to=='Institutional Settings' for r in sidebar.items),1)
        self.assertTrue(any(r.label=='Custom link' for r in sidebar.items))

    def test_monthly_legacy_and_already_paid_status(self):
        module=importlib.import_module(PREFIX+'v16_7_0_fix_monthly_bill_status_from_debt_ledger')
        paid=self.insert('Monthly Bill',docstatus=1,status='Paid')
        stale=self.insert('Monthly Bill',docstatus=1,status='Unpaid')
        partial=self.insert('Monthly Bill',docstatus=1,status='Unpaid')
        self.debt(reference_doctype='Monthly Bill',reference_name=stale)
        self.debt(reference_doctype='Monthly Bill',reference_name=partial,paid_amount=30,outstanding_amount=70,status='Partially Paid')
        module._migrate();module._migrate()
        for name,status in ((paid,'Paid'),(stale,'Paid'),(partial,'Partially Paid')):
            self.assertEqual(frappe.db.get_value('Monthly Bill',name,'status'),status)

    def test_reconnection_contract_null_blank_and_existing(self):
        suspension=self.insert('Service Suspension',service_contract=self.contract)
        names=[self.insert('Service Reconnection',service_contract=value,service_suspension=suspension) for value in (None,'','CORRECT')]
        self.body('backfill_reconnection_service_contract');self.body('backfill_reconnection_service_contract')
        self.assertEqual([frappe.db.get_value('Service Reconnection',n,'service_contract') for n in names],[self.contract,self.contract,'CORRECT'])

    def test_connection_bill_and_historical_reconnection_states(self):
        bill=self.insert('Connection Bill',docstatus=1,status='Unpaid')
        self.debt(entry_type='Connection Fee',reference_doctype='Connection Bill',reference_name=bill)
        self.body('backfill_connection_bill_status')
        self.assertEqual(frappe.db.get_value('Connection Bill',bill,'status'),'Paid')
        cases=[(0,'Partially Paid',0,'Draft'),(1,'Partially Paid',0,'Paid'),(1,'Executed',100,'Executed'),(2,'Paid',100,'Cancelled')]
        for docstatus,status,fee,expected in cases:
            name=self.insert('Service Reconnection',docstatus=docstatus,status=status,reconnection_fee=fee)
            self.body('backfill_service_reconnection_status')
            self.assertEqual(frappe.db.get_value('Service Reconnection',name,'status'),expected)

    def test_suspension_pre_sync_only_legacy_and_fine_evidence(self):
        frappe.client_cache.delete_value('table_columns::tabService Suspension')
        if not frappe.db.has_column('Service Suspension','reason'):
            frappe.db.sql('ALTER TABLE `tabService Suspension` ADD COLUMN reason varchar(140)')
            frappe.client_cache.delete_value('table_columns::tabService Suspension')
        converted=self.insert('Service Suspension',suspension_type='Arrears')
        legacy=self.insert('Service Suspension',suspension_type='By Request')
        frappe.db.sql("UPDATE `tabService Suspension` SET reason='Maintenance' WHERE name IN (%s,%s)",(converted,legacy))
        self.body('collapse_suspension_reason');self.body('collapse_suspension_reason')
        self.assertEqual(frappe.db.get_value('Service Suspension',converted,'suspension_type'),'Arrears')
        self.assertEqual(frappe.db.get_value('Service Suspension',legacy,'suspension_type'),'Subscriber Request')
        fine=self.insert('Service Suspension',suspension_type='Administrative')
        frappe.db.sql("UPDATE `tabService Suspension` SET reason='Sanction' WHERE name=%s",fine)
        with self.assertRaisesRegex(PatchError,'LegacySuspensionFineUnproven'):self.body('collapse_suspension_reason')
        self.assertEqual(frappe.db.get_value('Service Suspension',fine,'suspension_type'),'Administrative')
        linked=self.insert('Service Fine',docstatus=1,status='Unpaid',service_contract=self.contract)
        frappe.db.set_value('Service Suspension',fine,dict(service_contract=self.contract,service_fine=linked))
        count=frappe.db.count('Service Fine')
        self.body('collapse_suspension_reason')
        self.assertEqual(frappe.db.get_value('Service Suspension',fine,'suspension_type'),'By Fine')
        self.assertEqual(frappe.db.count('Service Fine'),count)

    def wrong_advances(self, amounts=(30,20), monthly=True):
        wrong=self.debt(entry_type='Connection Fee',paid_amount=sum(amounts),outstanding_amount=100-sum(amounts),status='Partially Paid')
        target=self.debt(paid_amount=0,outstanding_amount=100,status='Unpaid') if monthly else None
        items=[]
        for amount in amounts:
            receipt=self.insert('Payment Receipt',docstatus=1,service_contract=self.contract,payment_date=self.early.date())
            items.append(self.insert('Payment Receipt Item',parent=receipt,parenttype='Payment Receipt',parentfield='payment_items',
                payment_concept='Monthly Fee',billing_period='01-2026',amount=amount,balance=0,debt_ledger_entry=wrong))
        return wrong,target,items

    def test_multiple_advances_one_ledger_conserve_and_reapply_once(self):
        wrong,target,items=self.wrong_advances()
        self.body('release_monthly_advances_applied_to_other_charges')
        self.body('release_monthly_advances_applied_to_other_charges')
        self.assertEqual(frappe.db.get_value('Debt Ledger Entry',wrong,['paid_amount','outstanding_amount','status']),(0,100,'Unpaid'))
        self.assertEqual(frappe.db.get_value('Debt Ledger Entry',target,['paid_amount','outstanding_amount','status']),(50,50,'Partially Paid'))
        for item in items:self.assertEqual(frappe.db.get_value('Payment Receipt Item',item,['balance','debt_ledger_entry']),(0,target))

    def test_single_advance_no_monthly_and_rollback_on_allocator_failure(self):
        wrong,target,items=self.wrong_advances((100,),False)
        frappe.db.savepoint('release_failure')
        with patch.object(migration('release_monthly_advances_applied_to_other_charges'),'_apply_to_monthly_fee',side_effect=RuntimeError('isolated failure')):
            with self.assertRaises(RuntimeError):self.body('release_monthly_advances_applied_to_other_charges')
        frappe.db.rollback(save_point='release_failure')
        self.assertEqual(frappe.db.get_value('Debt Ledger Entry',wrong,'paid_amount'),100)
        self.assertEqual(frappe.db.get_value('Payment Receipt Item',items[0],'debt_ledger_entry'),wrong)
        self.body('release_monthly_advances_applied_to_other_charges')
        self.assertEqual(frappe.db.get_value('Payment Receipt Item',items[0],['balance','debt_ledger_entry']),(100,None))

    def test_refinancing_empty_exact_repeat_and_policy_preserved(self):
        debt=self.debt();ref=self.refinancing()
        frappe.db.set_single_value('Billing Settings','apply_late_fee',1)
        self.body('record_refinanced_debts');self.body('record_refinanced_debts')
        rows=frappe.get_all('Refinancing Settled Debt',filters={'parent':ref},fields=['debt_ledger_entry','settled_amount'])
        self.assertEqual([(r.debt_ledger_entry,r.settled_amount) for r in rows],[(debt,100)])
        self.assertEqual(frappe.db.get_single_value('Billing Settings','apply_late_fee'),1)

    def test_refinancing_partial_and_multiple_are_rejected_without_insertion(self):
        debt=self.debt();ref=self.refinancing()
        child=self.insert('Refinancing Settled Debt',parent=ref,parenttype='Debt Refinancing',parentfield='settled_debts',
            debt_ledger_entry=debt,settled_amount=50,entry_type='Monthly Fee',billing_period='01-2026')
        with self.assertRaisesRegex(PatchError,'RefinancingLinksIncomplete'):self.body('record_refinanced_debts')
        self.assertEqual(frappe.db.get_value('Refinancing Settled Debt',child,'settled_amount'),50)
        frappe.db.delete('Refinancing Settled Debt',{'name':child})
        self.refinancing()
        with self.assertRaisesRegex(PatchError,'RefinancingAttributionAmbiguous'):self.body('record_refinanced_debts')
        self.assertEqual(frappe.db.count('Refinancing Settled Debt',{'parent':ref}),0)

    def test_refinancing_receipts_are_subtracted_and_modified_is_not_a_cutoff(self):
        debt=self.debt();ref=self.refinancing(70)
        receipt=self.insert('Payment Receipt',docstatus=1,service_contract=self.contract)
        self.insert('Payment Receipt Item',parent=receipt,parenttype='Payment Receipt',parentfield='payment_items',
            amount=30,balance=0,debt_ledger_entry=debt)
        self.debt(amount=40,paid_amount=40,creation=self.cutoff+timedelta(days=1))
        frappe.db.set_value('Debt Refinancing',ref,'modified',self.cutoff+timedelta(days=100),update_modified=False)
        self.body('record_refinanced_debts')
        self.assertEqual(frappe.db.get_value('Refinancing Settled Debt',{'parent':ref},'settled_amount'),70)

    def test_multiple_correct_refinancings_are_preserved_and_duplicate_debt_rejected(self):
        first=self.debt();ref_a=self.refinancing()
        second=self.debt();ref_b=self.refinancing()
        names=[]
        for ref,debt in ((ref_a,first),(ref_b,second)):
            names.append(self.insert('Refinancing Settled Debt',parent=ref,parenttype='Debt Refinancing',parentfield='settled_debts',
                debt_ledger_entry=debt,entry_type='Monthly Fee',billing_period='01-2026',settled_amount=100))
        before=frappe.get_all('Refinancing Settled Debt',filters={'name':['in',names]},fields=['*'],order_by='name')
        self.body('record_refinanced_debts');self.body('record_refinanced_debts')
        self.assertEqual(frappe.get_all('Refinancing Settled Debt',filters={'name':['in',names]},fields=['*'],order_by='name'),before)
        frappe.db.set_value('Refinancing Settled Debt',names[1],'debt_ledger_entry',first)
        with self.assertRaisesRegex(PatchError,'RefinancingDebtAlreadyAttributed'):self.body('record_refinanced_debts')

    def test_refinancing_missing_cutoff_and_total_mismatch(self):
        self.debt(amount=120,paid_amount=120);ref=self.refinancing()
        with self.assertRaisesRegex(PatchError,'RefinancingTotalMismatch'):self.body('record_refinanced_debts')
        self.assertFalse(frappe.db.exists('Refinancing Settled Debt',{'parent':ref}))
        frappe.db.delete('Debt Ledger Entry',{'reference_name':ref})
        with self.assertRaisesRegex(PatchError,'RefinancingSubmissionEvidenceMissing'):self.body('record_refinanced_debts')

    def test_framework_skipped_retry_success_and_duplicate_completion_semantics(self):
        import sys
        from types import ModuleType
        from frappe.modules import patch_handler
        from qota.migration_identity import historical_completion
        identity='qota.tests.synthetic_patch_'+uuid.uuid4().hex
        module=ModuleType(identity)
        def failure():raise RuntimeError('Synthetic patch failure in disposable database')
        module.execute=failure
        with patch.dict(sys.modules,{identity:module}), \
            patch.object(patch_handler,'get_all_patches',return_value=[identity]):
            patch_handler.run_all(skip_failing=True)
            self.assertFalse(patch_handler.executed(identity))
            with self.assertRaises(PatchError):historical_completion(identity)
            calls=[]
            module.execute=lambda:calls.append('executed')
            patch_handler.run_all()
            self.assertTrue(historical_completion(identity))
            patch_handler.run_all()
            self.assertEqual(calls,['executed'])
            patch_handler.run_single(patchmodule=identity,force=True)
            with self.assertRaises(PatchError):historical_completion(identity)


def run_tests():
    site = os.environ.get('QOTA_TEST_SITE', 'qota.localhost')
    frappe.init(site=site, sites_path='/home/frappe/frappe-bench/sites')
    os.chdir('/home/frappe/frappe-bench/sites');frappe.connect()
    try:
        import sys
        suite=unittest.TestSuite(MigrationDatabaseTests(name) for name in sys.argv[1:]) if len(sys.argv)>1 else unittest.defaultTestLoader.loadTestsFromTestCase(MigrationDatabaseTests)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        return result.wasSuccessful()
    finally:frappe.db.rollback();frappe.destroy()


if __name__=='__main__':raise SystemExit(0 if run_tests() else 1)
