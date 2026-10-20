"""Pure contractual evidence, minimal Spanish projection and complaint boundaries."""

import copy
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import frappe

from qota.governance import contract_status_summary as status

CONTRACT = "SC-00125"
CUT = date(2026, 10, 11)


def snapshot():
	return dict(contract=dict(name=CONTRACT, docstatus=1, status="Active"), suspensions=[], reconnections=[], debts=[], items=[], settled=[])


def suspension(data, name="S1", **values):
	row = dict(name=name, service_contract=CONTRACT, docstatus=1, status="Scheduled", effective_date="2026-10-20", executed_date=None, amended_from=None)
	row.update(values); data["suspensions"].append(row)
	return row


def reconnection(data, **values):
	suspension(data, status="Executed", effective_date="2026-10-01", executed_date="2026-10-02")
	data["contract"].update(status="Suspended", suspended_since="2026-10-01")
	row = dict(name="R1", service_contract=CONTRACT, service_suspension="S1", docstatus=1, status="Paid", execution_date=None, amended_from=None, reconnection_fee="0")
	row.update(values); data["reconnections"].append(row)
	return row


def obligation(data, paid="0"):
	from decimal import Decimal
	out = Decimal(100) - Decimal(paid)
	data["reconnections"][0]["reconnection_fee"] = "100"
	d = dict(name="D1", service_contract=CONTRACT, reference_doctype="Service Reconnection", reference_name="R1", docstatus=0,
		entry_type="Reconnection Fee", amount="100", paid_amount=paid, outstanding_amount=str(out), due_date="2026-10-02",
		status="Paid" if out <= Decimal(".01") else "Partially Paid" if Decimal(paid) else "Unpaid")
	data["debts"].append(d)
	if Decimal(paid):
		data["items"].append(dict(name="I1", parent="P1", debt_ledger_entry="D1", service_contract=CONTRACT,
			receipt_docstatus=1, payment_date="2026-10-03", payment_concept="Reconnection Fee", amount=paid, balance="0"))
	return d


class ContractStatusTests(unittest.TestCase):
	def setUp(self):
		self.data = snapshot()
		p = patch.object(frappe, "_", lambda text, **kwargs: text)
		p.start(); self.addCleanup(p.stop)

	def read(self, cutoff=CUT, historical=None):
		before = copy.deepcopy(self.data)
		result = status.summarize(CONTRACT, cutoff, self.data, historical)
		self.assertEqual(self.data, before)
		self.assertEqual(status.StatusResult.restore(result.snapshot()), result)
		return result

	def test_canonical_active_suspended_without_orders(self):
		self.assertEqual(self.read().canonical_status, "Active")
		self.data["contract"]["status"] = "Suspended"
		self.assertEqual(self.read().canonical_status, "Suspended")

	def test_documental_eligibility(self):
		for docstatus, state in ((0, "Active"), (2, "Cancelled"), (1, "Closed"), (1, "Cancelled"), (1, "Draft")):
			with self.subTest(docstatus=docstatus, state=state):
				self.data["contract"].update(docstatus=docstatus, status=state)
				self.assertEqual(self.read().status, "Unavailable")

	def test_scheduled_before_on_after_never_execution(self):
		suspension(self.data)
		for day in (date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21)):
			self.assertEqual((self.read(day).suspension.stage, self.read(day).canonical_status), ("Scheduled", "Active"))

	def test_cancelled_only_specific_reference(self):
		suspension(self.data, docstatus=2, status="Draft")
		self.assertEqual(self.read().suspension.stage, "Absent")
		self.assertEqual(self.read(historical="S1").suspension.stage, "Cancelled")
		self.assertEqual(self.read(historical="other").suspension.availability, "Unavailable")

	def test_cancelled_parent_valid_amendment(self):
		suspension(self.data, docstatus=2, status="Draft")
		suspension(self.data, "S2", amended_from="S1", effective_date="2026-10-22")
		self.assertEqual(self.read().suspension.date, date(2026, 10, 22))

	def test_amendment_requires_cancelled_same_contract_ancestor(self):
		parent = suspension(self.data, docstatus=0, status="Draft")
		suspension(self.data, "S2", amended_from="S1")
		self.assertEqual(self.read().suspension.availability, "Unavailable")
		parent.update(docstatus=2, service_contract="SC-00999")
		self.assertEqual(self.read().suspension.availability, "Unavailable")

	def test_cycle_and_missing_ancestor_fail_closed(self):
		s = suspension(self.data, amended_from="S1")
		self.assertEqual(self.read().suspension.availability, "Unavailable")
		s["amended_from"] = "missing"
		self.assertEqual(self.read().suspension.availability, "Unavailable")

	def test_two_potential_orders_no_latest_guess(self):
		suspension(self.data); suspension(self.data, "S2", effective_date="2026-10-23")
		self.assertEqual(self.read().suspension.reason, "AmbiguousSuspension")

	def test_missing_scheduled_date_and_executed_date_mismatch(self):
		s = suspension(self.data, effective_date=None)
		self.assertEqual(self.read().suspension.availability, "Unavailable")
		s.update(effective_date="2026-10-20", executed_date="2026-10-21")
		self.assertEqual(self.read().suspension.availability, "Unavailable")

	def test_canonical_status_never_replaced_by_order(self):
		suspension(self.data, status="Executed", effective_date="2026-10-01", executed_date="2026-10-02")
		self.data["contract"]["suspended_since"] = "2026-10-01"
		r = self.read()
		self.assertEqual((r.canonical_status, r.suspension.reason), ("Active", "SuspensionContractMismatch"))

	def test_unpaid_and_partial_verified_obligation(self):
		reconnection(self.data, status="Unpaid"); d = obligation(self.data)
		self.assertEqual(self.read().reconnection.stage, "PaymentPending")
		d.update(paid_amount="35", outstanding_amount="65", status="Partially Paid")
		self.data["items"].append(dict(debt_ledger_entry="D1", service_contract=CONTRACT, receipt_docstatus=1,
			payment_date="2026-10-03", payment_concept="Reconnection Fee", amount="35", balance="0"))
		self.assertEqual(self.read().reconnection.stage, "PaymentPending")

	def test_paid_positive_requires_real_allocation(self):
		reconnection(self.data); obligation(self.data, "100")
		self.assertEqual(self.read().reconnection.stage, "ExecutionPending")
		self.data["items"].clear()
		self.assertEqual(self.read().reconnection.reason, "PaymentEvidenceMismatch")

	def test_zero_fee_not_monetary_receipt(self):
		reconnection(self.data)
		self.assertEqual(self.read().reconnection.stage, "ExecutionPending")

	def test_stale_paid_after_cancel_omitted(self):
		reconnection(self.data); obligation(self.data)
		self.assertEqual(self.read().reconnection.reason, "ReconnectionObligationMismatch")

	def test_scheduled_no_verified_programming(self):
		reconnection(self.data, status="Scheduled")
		self.assertEqual(self.read().reconnection.reason, "SchedulingEvidenceUnavailable")

	def test_executed_requires_specific_date_and_contract_evidence(self):
		r = reconnection(self.data, status="Executed", execution_date="2026-10-04")
		self.data["contract"].update(status="Active", reactivation_date="2026-10-04")
		self.assertEqual(self.read().reconnection.stage, "Executed")
		r["execution_date"] = None
		self.assertEqual(self.read().reconnection.availability, "Unavailable")

	def test_future_execution_not_verified(self):
		reconnection(self.data, status="Executed", execution_date="2026-10-12")
		self.data["contract"].update(status="Active", reactivation_date="2026-10-12")
		self.assertEqual(self.read().reconnection.availability, "Unavailable")

	def test_execution_lost_to_paid_is_not_reinvented(self):
		reconnection(self.data, execution_date="2026-10-04")
		self.data["contract"].update(status="Active", reactivation_date="2026-10-04")
		self.assertEqual(self.read().reconnection.reason, "ReconnectionEvidenceMismatch")

	def test_invalid_contract_and_suspension_relations(self):
		r = reconnection(self.data, service_contract="SC-00999")
		self.assertEqual(self.read().reconnection.reason, "ReconnectionRelationshipMismatch")
		r.update(service_contract=CONTRACT, service_suspension="other")
		self.assertEqual(self.read().reconnection.reason, "ReconnectionRelationshipMismatch")

	def test_two_reconnections_ambiguous(self):
		r = reconnection(self.data)
		self.data["reconnections"].append(dict(r, name="R2"))
		self.assertEqual(self.read().reconnection.reason, "AmbiguousReconnection")

	def test_invalid_obligation_and_refinancing_omitted(self):
		reconnection(self.data, status="Unpaid"); d = obligation(self.data)
		d["service_contract"] = "SC-00999"
		self.assertEqual(self.read().reconnection.reason, "InvalidObligation")
		d["service_contract"] = CONTRACT
		self.data["settled"].append(dict(debt_ledger_entry="D1"))
		self.assertEqual(self.read().reconnection.reason, "RefinancedObligation")

	def test_cancelled_reconnection_ignored(self):
		reconnection(self.data, docstatus=2, status="Cancelled")
		self.assertEqual(self.read().reconnection.stage, "Absent")

	def test_honduras_day_boundary(self):
		self.assertEqual(status.cut_date(datetime(2026, 10, 12, 5, 59, 59, tzinfo=timezone.utc)), CUT)
		self.assertEqual(status.cut_date(datetime(2026, 10, 12, 6, tzinfo=timezone.utc)), date(2026, 10, 12))

	def test_typed_results_reject_unverified_facts(self):
		with self.assertRaises(ValueError):
			status.OrderStage("Unavailable", "Executed", reason="MissingDate")
		with self.assertRaises(ValueError):
			status.OrderStage(stage="Scheduled", reference="S")
		with self.assertRaises(ValueError):
			status.StatusResult("Verified", CONTRACT, CUT, "Closed")

	def test_renderer_and_snapshot_no_private_fields(self):
		suspension(self.data, full_name="SECRET", suspension_type="Arrears", remarks="PRIVATE", amount="987.65")
		r = self.read()
		for value in ("SECRET", "PRIVATE", "Arrears", "987.65"):
			self.assertNotIn(value, str(r.snapshot()))


if __name__ == "__main__":
	unittest.main()
