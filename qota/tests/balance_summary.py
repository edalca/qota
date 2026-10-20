"""Synthetic financial invariants over canonical snapshot shapes."""

import copy
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import frappe

from qota.billing import balance_summary as billing

CONTRACT = "SC-00125"
CUT = date(2026, 10, 11)


def snapshot():
	return dict(contract=dict(name=CONTRACT, docstatus=1, status="Active", start_date="2026-08-01"),
		settings=dict(default_currency="HNL", cycle_start_day=1, days_until_due=10),
		debts=[], sources=[], items=[], refinancings=[], settled=[], schedule=[], statement=[])


def charge(data, amount="100", concept="Monthly Fee", period="08-2026", due="2026-09-10", name=None):
	name = name or "D" + str(len(data["debts"]))
	ref = {"Monthly Fee": "Monthly Bill", "Service Fine": "Service Fine", "Connection Fee": "Connection Bill",
		"Reconnection Fee": "Service Reconnection"}.get(concept)
	data["debts"].append(dict(name=name, docstatus=0, entry_type=concept, billing_period=period,
		amount=amount, paid_amount="0", outstanding_amount=amount, status="Unpaid", due_date=due,
		reference_doctype=ref, reference_name=name + "source" if ref else None))
	if ref:
		month, year = map(int, period.split("-"))
		from calendar import monthrange
		data["sources"].append(dict(doctype=ref, name=name + "source", docstatus=1, service_contract=CONTRACT,
			amount=amount, period=period, start_date=date(year, month, 1), end_date=date(year, month, monthrange(year, month)[1])))
	data["statement"].append(dict(debit=amount, credit="0"))
	return data["debts"][-1]


def payment(data, amount="100", balance="0", debt=None, period="08-2026", concept="Monthly Fee", cancelled=False, when="2026-09-01"):
	item = dict(name="I" + str(len(data["items"])), parent="P" + str(len(data["items"])), idx=1,
		docstatus=2 if cancelled else 1, payment_date=when, amount=amount, balance=balance,
		payment_concept=concept, billing_period=period, debt_ledger_entry=debt["name"] if debt else None)
	data["items"].append(item)
	if not cancelled:
		data["statement"].append(dict(debit="0", credit=amount))
		if debt:
			paid = Decimal(debt["paid_amount"]) + Decimal(amount) - Decimal(balance)
			out = Decimal(debt["amount"]) - paid
			debt.update(paid_amount=str(paid), outstanding_amount=str(out), status="Paid" if out <= Decimal(".01") else "Partially Paid" if paid > 0 else "Unpaid")
	return item


class BalanceSummaryTests(unittest.TestCase):
	def setUp(self):
		self.data = snapshot()
		self.month = charge(self.data)
		self.second = charge(self.data, period="09-2026", due="2026-10-10")

	def read(self, data=None):
		data = data or self.data
		before = copy.deepcopy(data)
		result = billing.reconcile(CONTRACT, CUT, data)
		self.assertEqual(data, before)
		return result

	def test_full_months(self):
		r = self.read()
		self.assertEqual((r.status, r.monthly, r.total, r.required_periods), ("Verified", Decimal(200), Decimal(200), 0))
		self.assertEqual(billing.BalanceResult.restore(r.snapshot()), r)

	def test_partial_payment(self):
		payment(self.data, "35", debt=self.month)
		self.assertEqual(self.read().monthly, Decimal(165))

	def test_fully_paid_and_zero_verified(self):
		payment(self.data, debt=self.month)
		payment(self.data, debt=self.second, period="09-2026")
		self.assertEqual(self.read().total, 0)

	def test_unused_same_period_advance(self):
		payment(self.data, "80", "80")
		self.assertEqual(self.read().monthly, Decimal(120))

	def test_multiple_advances_oldest_first_and_no_mutation(self):
		payment(self.data, "60", "60", when="2026-08-02")
		payment(self.data, "60", "60", when="2026-08-01")
		self.assertEqual(self.read().monthly, 100)
		self.assertEqual([i["balance"] for i in self.data["items"]], ["60", "60"])

	def test_future_period_advance_does_not_cover_current(self):
		payment(self.data, "1000", "1000", period="11-2026")
		self.assertEqual(self.read().monthly, 200)

	def test_already_applied_advance_not_subtracted_twice(self):
		payment(self.data, "120", "20", debt=self.month)
		self.assertEqual(self.read().monthly, 100)

	def test_negative_net_does_not_cover_fines_or_surcharges(self):
		payment(self.data, "1000", "1000")
		fine = charge(self.data, "125", "Service Fine")
		charge(self.data, "75", "Late Fee")
		r = self.read()
		self.assertEqual((r.monthly, r.fines, r.surcharges, r.total), (Decimal(100), Decimal(125), Decimal(75), Decimal(300)))
		self.assertLess(r.statement_net, 0)

	def test_months_covered_fine_and_surcharge_remain(self):
		payment(self.data, debt=self.month)
		payment(self.data, debt=self.second, period="09-2026")
		charge(self.data, "125", "Service Fine")
		charge(self.data, "75", "Late Fee")
		r = self.read()
		self.assertEqual((r.monthly, r.fines, r.surcharges, r.total), (0, 125, 75, 200))

	def test_monthly_fine_surcharge_separate(self):
		charge(self.data, "125", "Service Fine")
		charge(self.data, "75", "Late Fee")
		self.assertEqual(self.read().total, 400)

	def test_future_obligation_excluded(self):
		charge(self.data, period="10-2026", due="2026-11-10")
		self.assertEqual(self.read().total, 200)

	def test_cancelled_receipt_does_not_pay(self):
		payment(self.data, debt=self.month, cancelled=True)
		self.assertEqual(self.read().total, 200)

	def test_cancelled_source_with_lingering_ledger_unavailable(self):
		self.data["sources"][0]["docstatus"] = 2
		self.assertEqual(self.read().reason, "InvalidSource")

	def test_receipt_cancelled_but_persistent_paid_not_reversed(self):
		payment(self.data, debt=self.month)
		self.data["items"][0]["docstatus"] = 2
		self.assertEqual(self.read().reason, "AllocationMismatch")

	def test_duplicates_and_contradictory_amounts(self):
		for field, value, reason in (("outstanding_amount", "90", "OutstandingMismatch"), ("paid_amount", "10", "OutstandingMismatch"), ("status", "Paid", "LedgerStatusMismatch")):
			with self.subTest(field=field):
				d = copy.deepcopy(self.data); d["debts"][0][field] = value
				self.assertEqual(self.read(d).reason, reason)
		charge(self.data)
		self.assertEqual(self.read().reason, "DuplicateMonthlyPeriod")

	def test_currency_configuration_and_contradiction(self):
		self.data["settings"]["default_currency"] = "USD"
		self.assertEqual(self.read().reason, "CurrencyUnavailable")
		self.data["settings"]["default_currency"] = "HNL"
		self.month["currency"] = "USD"
		self.assertEqual(self.read().reason, "CurrencyMismatch")

	def test_billing_tolerance_without_hiding_material_difference(self):
		payment(self.data, "99.99", debt=self.month)
		self.assertEqual(self.read().monthly, 100)
		self.month["outstanding_amount"] = "0.02"
		self.assertEqual(self.read().reason, "OutstandingMismatch")

	def test_cut_date_and_honduras(self):
		self.assertEqual(billing.cut_date(datetime(2026, 10, 12, 5, 59, tzinfo=timezone.utc)), CUT)
		self.assertEqual(billing.cut_date("2026-10-11 12:00:00"), CUT)
		self.assertEqual(billing.cut_date(CUT), CUT)

	def test_empty_history_future_start_is_complete(self):
		d = snapshot(); d["contract"]["start_date"] = "2026-10-01"
		self.assertEqual(self.read(d).total, 0)

	def test_unbilled_periods_do_not_hide_recorded_debt(self):
		self.assertEqual(self.read(snapshot()).total, 0)
		self.data["debts"].pop(); self.data["statement"].pop(); self.data["sources"].pop()
		self.data["contract"]["start_date"] = "2025-01-01"
		self.data["missing_periods"] = ["01-2025", "09-2026"]
		self.assertEqual((self.read().status, self.read().monthly), ("Verified", Decimal(100)))

	def test_period_configuration_and_start_do_not_gate_ledger_balance(self):
		self.data["contract"]["start_date"] = None
		self.data["settings"] = dict(default_currency="HNL")
		self.assertEqual((self.read().status, self.read().total), ("Verified", Decimal(200)))

	def test_submitted_charge_without_ledger_still_fails_closed(self):
		self.data["debts"].pop(); self.data["statement"].pop()
		self.assertEqual(self.read().reason, "MissingLedgerEffect")

	def test_additional_charges_due_and_future(self):
		for concept in ("Connection Fee", "Reconnection Fee", "Other Fee"):
			with self.subTest(concept=concept):
				d = copy.deepcopy(self.data); charge(d, "100", concept, due="2027-01-01")
				self.assertEqual(self.read(d).total, 200)
				d["debts"][-1]["due_date"] = CUT
				r = self.read(d)
				self.assertEqual((r.status, r.additional, r.total), ("Verified", ((concept, Decimal(100)),), Decimal(300)))

	def test_unknown_concept_cannot_disappear_from_total(self):
		charge(self.data, "30", "Unapproved Charge")
		self.assertEqual(self.read().reason, "UnknownConcept")

	def test_public_rounding_must_reconcile_with_total(self):
		self.month["amount"] = self.month["outstanding_amount"] = "100.015"
		self.data["sources"][0]["amount"] = "100.015"
		self.data["statement"][0]["debit"] = "100.015"
		charge(self.data, "0.015", "Service Fine")
		self.assertEqual(self.read().reason, "MonetaryProjectionMismatch")

	def test_refinancing_links_reconcile_original_without_double_debt(self):
		ref = dict(name="REF", docstatus=1, posting_date="2026-09-01", current_total_debt="200", down_payment="0")
		self.data["refinancings"].append(ref)
		self.data["sources"].append(dict(doctype="Debt Refinancing", service_contract=CONTRACT, amount="200", **ref))
		for d in self.data["debts"]:
			self.data["settled"].append(dict(parent="REF", debt_ledger_entry=d["name"], entry_type=d["entry_type"], billing_period=d["billing_period"], settled_amount=d["outstanding_amount"]))
			d.update(paid_amount=d["amount"], outstanding_amount="0", status="Paid")
		self.data["statement"].append(dict(debit="0", credit="200"))
		installment = charge(self.data, "200", "Refinancing Installment", due="2026-11-01")
		installment.update(reference_doctype="Debt Refinancing", reference_name="REF")
		self.data["schedule"].append(dict(parent="REF", due_date="2026-11-01", amount="200"))
		self.assertEqual(self.read().total, 0)
		self.data["debts"][-1]["due_date"] = "2026-10-01"
		self.data["schedule"][-1]["due_date"] = "2026-10-01"
		self.assertEqual(self.read().total, 200)
		self.assertEqual(self.read().additional, (("Refinancing Installment", Decimal(200)),))
		payment(self.data, "200", debt=installment, concept="Refinancing Installment")
		self.assertEqual(self.read().total, 0)
		self.data["settled"].clear()
		self.assertEqual(self.read().reason, "MissingSettlementLinks")

	def test_concept_and_period_mismatch(self):
		item = payment(self.data, debt=self.month)
		item["payment_concept"] = "Service Fine"
		self.assertEqual(self.read().reason, "ConceptMismatch")
		item["payment_concept"], item["billing_period"] = "Monthly Fee", "10-2026"
		self.assertEqual(self.read().reason, "PeriodMismatch")

	def test_statement_is_reconciliation_not_current_total(self):
		self.data["statement"][0]["debit"] = "101"
		self.assertEqual(self.read().reason, "StatementMismatch")

	def test_payments_after_historical_cut_cannot_be_reconstructed(self):
		payment(self.data, debt=self.month, when="2026-10-12")
		self.assertEqual(self.read().reason, "PaymentAfterCut")

	def test_result_cannot_fabricate_verified_or_unavailable_totals(self):
		with self.assertRaises(ValueError):
			billing.BalanceResult("Verified", CONTRACT, CUT)
		with self.assertRaises(ValueError):
			billing.BalanceResult("Unavailable", CONTRACT, CUT, total=Decimal(0), reason="MissingPeriods")

	def test_read_failure_classification_and_permission_propagation(self):
		with patch.object(billing, "_permissions"), patch.object(billing, "_load", side_effect=TimeoutError):
			r = billing.read_balance(CONTRACT, CUT)
			self.assertEqual(r.status, "TechnicalFailure"); self.assertTrue(r.transient)
		with patch.object(billing, "_permissions"), patch.object(billing, "_load", side_effect=RuntimeError):
			self.assertFalse(billing.read_balance(CONTRACT, CUT).transient)
		with patch.object(billing, "_permissions", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				billing.read_balance(CONTRACT, CUT)
