"""Real business lifecycle probes on isolated synthetic records."""

from contextlib import ExitStack
from datetime import datetime, timedelta
import os
import sys
import unittest
import uuid
from unittest.mock import patch

import frappe


def connect_local():
	site = os.environ.get("QOTA_TEST_SITE", "qota.localhost")
	sites_path = "/home/frappe/frappe-bench/sites"
	frappe.init(site=site, sites_path=sites_path)
	os.chdir(sites_path)
	frappe.connect()
	frappe.set_user("Administrator")


class _Fixtures:
	def __init__(self):
		self.prefix = f"QOTA-PROC-{uuid.uuid4().hex[:8]}-"
		self.rows = []

	def insert(self, doctype, **values):
		name = values.pop("name", f"{self.prefix}{uuid.uuid4().hex[:8]}")
		doc = frappe.get_doc(dict(doctype=doctype, name=name, **values))
		doc.db_insert()
		self.rows.append((doctype, doc.name))
		return doc.name

	def contract(self):
		code = str(uuid.uuid4().int)[:5].zfill(5)
		name = f"SC-{code}"
		while frappe.db.exists("Service Contract", name):
			code = str(uuid.uuid4().int)[:5].zfill(5)
			name = f"SC-{code}"
		doc = frappe.get_doc(dict(doctype="Service Contract", name=name, docstatus=0, status="Draft"))
		doc.db_insert()
		self.rows.append(("Service Contract", name))
		return name, code


class ContractProcessTests(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self.stack = ExitStack()
		self.stack.enter_context(patch.object(frappe.db, "commit", lambda: None))
		self.addCleanup(self.stack.close)
		self.addCleanup(frappe.db.rollback)
		self.fx = _Fixtures()
		self.clock = datetime(2026, 10, 11, 10, 0, 0)
		self.day = self.clock.date()
		self.stack.enter_context(patch("frappe.utils.today", return_value=str(self.day)))
		self.contract, self.code = self.fx.contract()
		subscriber = self.fx.insert("Subscriber", full_name="Synthetic status fixture")
		premises = self.fx.insert("Premises")
		category = self.fx.insert("Service Category")
		frappe.db.set_value("Service Contract", self.contract, dict(subscriber=subscriber, premises=premises,
			service_category=category, billing_basis="Flat Rate", start_date=self.clock.date(), status="Active"))
		frappe.get_doc("Service Contract", self.contract).submit()

	def fingerprint(self):
		return (
			frappe.db.get_value("Service Contract", self.contract, ["status", "suspended_since", "reactivation_date"]),
			frappe.get_all("Service Suspension", filters={"service_contract": self.contract},
				fields=["name", "docstatus", "status", "effective_date", "executed_date"], order_by="name"),
			frappe.get_all("Service Reconnection", filters={"service_contract": self.contract},
				fields=["name", "docstatus", "status", "execution_date", "reconnection_fee"], order_by="name"),
			frappe.get_all("Debt Ledger Entry", filters={"service_contract": self.contract},
				fields=["name", "paid_amount", "outstanding_amount", "status"], order_by="name"),
			frappe.db.count("Meter Reading", {"service_contract": self.contract}),
		)

	def suspension(self, metered=False, execute=False):
		if metered:
			frappe.db.set_value("Service Contract", self.contract, "billing_basis", "Metered")
		doc = frappe.get_doc(dict(doctype="Service Suspension", service_contract=self.contract,
			suspension_type="Subscriber Request", posting_date=self.clock, effective_date=self.day,
			billing_basis="Metered" if metered else "Flat Rate", status="Draft"))
		doc.insert(); self.fx.rows.append((doc.doctype, doc.name)); doc.submit()
		if execute:
			doc.execute_suspension_logic(10 if metered else 0, str(self.day))
		return doc

	def reconnection(self, suspension, fee=0):
		if fee:
			# A synthetic historical reason isolates the fee branch; creation,
			# submit, obligation and payment below use the installed controllers.
			frappe.db.set_value("Service Suspension", suspension.name, "suspension_type", "Arrears")
		doc = frappe.get_doc(dict(doctype="Service Reconnection", service_contract=self.contract,
			service_suspension=suspension.name, billing_basis="Flat Rate", reconnection_fee=fee, status="Draft"))
		doc.insert(); self.fx.rows.append((doc.doctype, doc.name)); doc.submit()
		return doc

	def pay(self, reconnection, amount):
		debt = frappe.db.get_value("Debt Ledger Entry", dict(reference_doctype="Service Reconnection", reference_name=reconnection.name), "name")
		doc = frappe.get_doc(dict(doctype="Payment Receipt", service_contract=self.contract,
			payment_date=self.clock, mode_of_payment="Cash", payment_items=[dict(payment_concept="Reconnection Fee",
			amount=amount, debt_ledger_entry=debt)]))
		doc.insert(); self.fx.rows.append((doc.doctype, doc.name)); doc.submit()
		return doc, debt

	def test_formal_contract_submit_and_suspension_execute_flat(self):
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, ["docstatus", "status"]), (1, "Active"))
		doc = self.suspension()
		self.assertEqual(doc.status, "Scheduled")
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, "status"), "Active")
		doc.execute_suspension_logic(0, str(self.day + timedelta(days=2)))
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, ["status", "suspended_since"]), ("Suspended", self.day))
		self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, ["status", "executed_date"]), ("Executed", self.day + timedelta(days=2)))
		with self.assertRaises(frappe.ValidationError):
			doc.cancel()

	def test_scheduled_cancel_and_real_amendment(self):
		doc = self.suspension(); doc.cancel()
		self.assertEqual((doc.docstatus, doc.status), (2, "Draft"))
		new = frappe.copy_doc(doc)
		new.docstatus = 0
		new.amended_from = doc.name
		new.effective_date = self.day + timedelta(days=3)
		new.insert(); new.submit()
		self.assertEqual((new.docstatus, new.status, new.amended_from), (1, "Scheduled", doc.name))

	def test_pending_order_duplicate_rejected_and_double_submit(self):
		doc = self.suspension()
		with self.assertRaises(frappe.ValidationError):
			self.suspension()
		doc.submit()
		self.assertEqual(frappe.db.count(doc.doctype, {"service_contract": self.contract}), 1)

	def test_metered_cut_uses_execution_date_and_rollback_restores_effects(self):
		doc = self.suspension(metered=True)
		frappe.db.savepoint("metered_cut")
		doc.execute_suspension_logic(10, str(self.day))
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, "status"), "Suspended")
		self.assertEqual(frappe.db.get_value("Meter Reading", {"service_contract": self.contract}, "reading_date"), self.day)
		frappe.db.rollback(save_point="metered_cut")
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, "status"), "Active")
		self.assertEqual(frappe.db.count("Meter Reading", {"service_contract": self.contract}), 0)

	def test_metered_cut_single_reading_and_repeated_execution_rejected(self):
		doc = self.suspension(metered=True)
		doc.execute_suspension_logic(10, str(self.day))
		self.assertEqual(frappe.db.count("Meter Reading", {"service_contract": self.contract}), 1)
		frappe.db.savepoint("repeat_cut")
		with self.assertRaises(frappe.ValidationError):
			doc.execute_suspension_logic(10, str(self.day))
		frappe.db.rollback(save_point="repeat_cut")
		self.assertEqual(frappe.db.count("Meter Reading", {"service_contract": self.contract}), 1)

	def test_zero_fee_paid_has_no_receipt_execution_updates_active_once(self):
		doc = self.reconnection(self.suspension(execute=True))
		self.assertEqual(doc.status, "Paid")
		self.assertEqual(frappe.db.count("Debt Ledger Entry", {"reference_name": doc.name}), 0)
		self.assertEqual(frappe.db.count("Payment Receipt", {"service_contract": self.contract}), 0)
		doc.execute_reconnection_logic(0, str(self.day))
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, "status"), "Active")
		self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, ["status", "execution_date"]), ("Executed", self.day))
		with self.assertRaises(frappe.ValidationError):
			doc.execute_reconnection_logic(0, str(self.day))

	def test_partial_full_payment_and_cancel_restores_unpaid(self):
		doc = self.reconnection(self.suspension(execute=True), 100)
		self.assertEqual(doc.status, "Unpaid")
		partial, debt = self.pay(doc, 35)
		self.assertEqual(frappe.db.get_value("Debt Ledger Entry", debt, "status"), "Partially Paid")
		self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "status"), "Unpaid")
		full, _ = self.pay(doc, 65)
		self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "status"), "Paid")
		full.cancel(); partial.cancel()
		self.assertEqual(frappe.db.get_value("Debt Ledger Entry", debt, ["paid_amount", "outstanding_amount", "status"]), (0, 100, "Unpaid"))
		self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "status"), "Unpaid")
		doc.reload()
		with self.assertRaises(frappe.ValidationError):
			doc.execute_reconnection_logic(0, str(self.day))

	def test_paid_sync_preserves_executed_and_cancel_after_preserves_execution(self):
		doc = self.reconnection(self.suspension(execute=True), 100)
		receipt, debt = self.pay(doc, 100)
		doc.reload(); doc.execute_reconnection_logic(0, str(self.day))
		frappe.get_doc("Debt Ledger Entry", debt).sync_reference_document_status()
		self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, ["status", "execution_date"]), ("Executed", self.day))
		receipt.cancel()
		self.assertEqual(frappe.db.get_value("Debt Ledger Entry", debt, "outstanding_amount"), 100)
		self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "execution_date"), self.day)

	def test_cross_contract_suspension_rejected_before_obligation(self):
		suspension = self.suspension(execute=True)
		other, _ = self.fx.contract()
		frappe.db.set_value("Service Contract", other, dict(docstatus=1, status="Suspended"))
		doc = frappe.get_doc(dict(doctype="Service Reconnection", service_contract=other,
			service_suspension=suspension.name, billing_basis="Flat Rate", reconnection_fee=100))
		frappe.db.set_value(suspension.doctype, suspension.name, "suspension_type", "Arrears")
		with self.assertRaises(frappe.ValidationError):
			doc.insert()
		self.assertFalse(frappe.db.exists("Debt Ledger Entry", {"reference_name": doc.name}))

	def test_reconnection_double_submit_cancel_and_amend(self):
		doc = self.reconnection(self.suspension(execute=True), 100)
		doc.submit()
		self.assertEqual(frappe.db.count("Debt Ledger Entry", {"reference_name": doc.name}), 1)
		doc.cancel()
		self.assertEqual(doc.status, "Cancelled")
		new = frappe.copy_doc(doc)
		new.docstatus = 0
		new.status = "Draft"
		new.amended_from = doc.name
		new.insert(); new.submit()
		self.assertEqual(new.status, "Unpaid")

	def test_scheduled_select_has_no_scheduling_source_but_accepts_execution(self):
		doc = self.reconnection(self.suspension(execute=True))
		frappe.db.set_value(doc.doctype, doc.name, "status", "Scheduled")
		doc.reload()
		self.assertFalse(frappe.get_meta(doc.doctype).has_field("scheduled_date"))
		doc.execute_reconnection_logic(0, str(self.day))
		self.assertEqual(doc.status, "Executed")

	def test_submission_payment_partial_full_execution_and_receipt_cancel(self):
		s = self.suspension()
		self.assertEqual(frappe.db.get_value(s.doctype, s.name, "status"), "Scheduled")
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, "status"), "Active")
		s.execute_suspension_logic(0, str(self.day))
		self.assertEqual(frappe.db.get_value(s.doctype, s.name, "status"), "Executed")
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, "status"), "Suspended")
		r = self.reconnection(s, 100)
		self.assertEqual(frappe.db.get_value(r.doctype, r.name, "status"), "Unpaid")
		partial, debt = self.pay(r, 35)
		self.assertEqual(frappe.db.get_value("Debt Ledger Entry", debt, "status"), "Partially Paid")
		self.assertEqual(frappe.db.get_value(r.doctype, r.name, "status"), "Unpaid")
		full, _ = self.pay(r, 65)
		self.assertEqual(frappe.db.get_value(r.doctype, r.name, "status"), "Paid")
		r.reload()
		r.execute_reconnection_logic(0, str(self.day))
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, "status"), "Active")
		self.assertEqual(frappe.db.get_value(r.doctype, r.name, ["status", "execution_date"]), ("Executed", self.day))
		full.cancel()
		self.assertEqual(frappe.db.get_value("Debt Ledger Entry", debt, ["paid_amount", "outstanding_amount", "status"]), (35, 65, "Partially Paid"))
		self.assertEqual(frappe.db.get_value(r.doctype, r.name, ["status", "execution_date"]), ("Executed", self.day))
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, "status"), "Active")
		self.assertEqual(partial.docstatus, 1)

	def test_metered_reconnection_creates_one_reading_and_rollback(self):
		s = self.suspension(metered=True, execute=True)
		self.assertEqual(frappe.db.get_value(s.doctype, s.name, "status"), "Executed")
		r = self.reconnection(s)
		execution = self.day + timedelta(days=10)
		frappe.db.savepoint("metered_reconnect")
		r.execute_reconnection_logic(10, str(execution))
		self.assertEqual(frappe.db.count("Meter Reading", {"service_contract": self.contract}), 2)
		self.assertEqual(frappe.db.get_value(r.doctype, r.name, ["status", "execution_date"]), ("Executed", execution))
		with self.assertRaises(frappe.ValidationError):
			r.execute_reconnection_logic(10, str(execution))
		frappe.db.rollback(save_point="metered_reconnect")
		self.assertEqual(frappe.db.get_value("Service Contract", self.contract, "status"), "Suspended")
		self.assertEqual(frappe.db.count("Meter Reading", {"service_contract": self.contract}), 1)

	def test_failed_reconnection_save_rolls_back_contract_reading_and_order(self):
		r = self.reconnection(self.suspension(metered=True, execute=True))
		before = self.fingerprint()
		frappe.db.savepoint("failed_reconnect")
		with patch.object(type(r), "save", side_effect=RuntimeError("Synthetic durable-write failure")):
			with self.assertRaises(RuntimeError):
				r.execute_reconnection_logic(10, str(self.day + timedelta(days=10)))
		frappe.db.rollback(save_point="failed_reconnect")
		self.assertEqual(self.fingerprint(), before)

	def test_scheduled_cancel_preserves_independent_meter_readings(self):
		frappe.db.set_value("Service Contract", self.contract, "billing_basis", "Metered")
		reading = frappe.get_doc(dict(doctype="Meter Reading", service_contract=self.contract, reading_date=self.day, current_reading=10))
		reading.insert(); reading.submit()
		s = self.suspension(metered=True); s.cancel()
		self.assertEqual(frappe.db.get_value("Meter Reading", reading.name, "docstatus"), 1)

	def test_another_suspension_of_same_contract_and_duplicate_reconnection_rejected(self):
		s = self.suspension(execute=True)
		older = self.fx.insert("Service Suspension", service_contract=self.contract, docstatus=1, status="Executed",
			effective_date=self.day - timedelta(days=30), executed_date=self.day - timedelta(days=30))
		doc = frappe.get_doc(dict(doctype="Service Reconnection", service_contract=self.contract, service_suspension=older))
		with self.assertRaises(frappe.ValidationError):
			doc.insert()
		self.reconnection(s)
		with self.assertRaises(frappe.ValidationError):
			self.reconnection(s)

	def test_stale_paid_cannot_bypass_current_unsettled_obligation(self):
		r = self.reconnection(self.suspension(execute=True), 100)
		receipt, _ = self.pay(r, 100); receipt.cancel()
		frappe.db.set_value(r.doctype, r.name, "status", "Paid")
		r.reload()
		before = self.fingerprint()
		with self.assertRaisesRegex(frappe.ValidationError, "obligation must be settled"):
			r.execute_reconnection_logic(0, str(self.day))
		self.assertEqual(self.fingerprint(), before)


def run_local_tests():
	connect_local()
	try:
		suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:], module=sys.modules[__name__]) if len(sys.argv) > 1 else unittest.defaultTestLoader.loadTestsFromTestCase(ContractProcessTests)
		return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
	finally:
		frappe.db.rollback(); frappe.destroy()


if __name__ == "__main__":
	raise SystemExit(0 if run_local_tests() else 1)
