"""Minimal read-only balance reconciliation over Billing's persisted effects.

No document lifecycle, pricing engine, balance refresh or ledger update is used.
The caller owns a consistent read transaction. Historical cuts cannot reconstruct
payments or settlements after the cut and therefore fail closed. Additional
concepts use their persisted due date and a grouped minimal public projection.
Unbilled periods do not represent recorded debt or prevent reading the ledger.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal

from qota.governance.institutional import local_datetime

ZERO = Decimal("0")
SETTLEMENT_TOLERANCE = Decimal("0.01")
# MariaDB Currency columns retain nine decimal places; floats from legacy
# report readers may add insignificant representation noise, never whole cents.
RECONCILIATION_TOLERANCE = Decimal("0.00000001")
CONCEPTS = {"Monthly Fee", "Service Fine", "Late Fee", "Connection Fee", "Reconnection Fee",
	"Other Fee", "Refinancing Down Payment", "Refinancing Installment"}
ADDITIONAL = CONCEPTS - {"Monthly Fee", "Service Fine", "Late Fee"}


class IncompleteBalance(ValueError):
	def __init__(self, reason):
		self.reason = reason
		super().__init__(reason)


@dataclass(frozen=True)
class BalanceResult:
	status: Literal["Verified", "Unavailable", "TechnicalFailure"]
	contract: str
	cutoff: date
	currency: str | None = None
	monthly: Decimal | None = None
	fines: Decimal | None = None
	surcharges: Decimal | None = None
	additional: tuple[tuple[str, Decimal], ...] = ()
	total: Decimal | None = None
	reason: str | None = None
	required_periods: int = 0
	ledger_count: int = 0
	evidence_digest: str | None = None
	statement_net: Decimal | None = None
	transient: bool = False
	ledger_amount: Decimal | None = None
	receipt_amount: Decimal | None = None
	unused_receipt_balance: Decimal | None = None
	settlement_amount: Decimal | None = None
	monthly_advance_coverage: Decimal | None = None
	ledger_references: tuple[str, ...] = ()

	def __post_init__(self):
		if self.status not in {"Verified", "Unavailable", "TechnicalFailure"} or not re.fullmatch(r"SC-[0-9]{5}", self.contract):
			raise ValueError("Invalid balance identity.")
		if type(self.cutoff) is not date:
			raise ValueError("Invalid balance cut.")
		# required_periods remains for restoring historical preparations; new reads
		# impose no billing-period coverage requirement and leave it at zero.
		if type(self.transient) is not bool or any(type(v) is not int or v < 0 for v in (self.required_periods, self.ledger_count)):
			raise ValueError("Invalid balance evidence.")
		if self.status == "Verified":
			if self.currency != "HNL" or self.reason or self.transient or not re.fullmatch(r"[0-9a-f]{64}", self.evidence_digest or ""):
				raise ValueError("A verified balance requires evidence and currency.")
			values = (self.monthly, self.fines, self.surcharges, *(v for _, v in self.additional))
			if any(not isinstance(v, Decimal) or not v.is_finite() or v < 0 for v in values) or self.total != sum(values, ZERO):
				raise ValueError("Invalid verified totals.")
			evidence = (self.ledger_amount, self.receipt_amount, self.unused_receipt_balance, self.settlement_amount, self.monthly_advance_coverage)
			if any(not isinstance(v, Decimal) or not v.is_finite() or v < 0 for v in evidence) or not isinstance(self.statement_net, Decimal) or not self.statement_net.is_finite():
				raise ValueError("Invalid reconciliation evidence.")
			if type(self.ledger_references) is not tuple or len(set(self.ledger_references)) != self.ledger_count:
				raise ValueError("Invalid ledger references.")
			if abs(self.statement_net - (self.ledger_amount - self.receipt_amount - self.settlement_amount)) > RECONCILIATION_TOLERANCE:
				raise ValueError("Invalid reconciliation evidence.")
		elif not self.reason or any(v is not None for v in (self.monthly, self.fines, self.surcharges, self.total, self.statement_net,
			self.ledger_amount, self.receipt_amount, self.unused_receipt_balance, self.settlement_amount, self.monthly_advance_coverage)) or self.additional or self.ledger_references:
			raise ValueError("An unavailable balance cannot expose totals.")

	def snapshot(self):
		value = asdict(self)
		value["cutoff"] = self.cutoff.isoformat()
		for key in ("monthly", "fines", "surcharges", "total", "statement_net", "ledger_amount", "receipt_amount", "unused_receipt_balance", "settlement_amount", "monthly_advance_coverage"):
			if value[key] is not None:
				value[key] = str(value[key])
		value["additional"] = [[k, str(v)] for k, v in self.additional]
		return value

	@classmethod
	def restore(cls, value):
		value = dict(value)
		value["cutoff"] = date.fromisoformat(value["cutoff"])
		for key in ("monthly", "fines", "surcharges", "total", "statement_net", "ledger_amount", "receipt_amount", "unused_receipt_balance", "settlement_amount", "monthly_advance_coverage"):
			if value[key] is not None:
				value[key] = Decimal(value[key])
		value["additional"] = tuple((k, Decimal(v)) for k, v in value["additional"])
		value["ledger_references"] = tuple(value["ledger_references"])
		return cls(**value)


def cut_date(value=None):
	if value is None or isinstance(value, datetime):
		return local_datetime(value).date()
	if type(value) is date:
		return value
	if isinstance(value, str):
		return cut_date(datetime.fromisoformat(value)) if "T" in value or " " in value else date.fromisoformat(value)
	raise ValueError("Invalid balance cut.")


def _require(condition, reason):
	if not condition:
		raise IncompleteBalance(reason)


def money(value):
	try:
		_require(value is not None and not isinstance(value, bool), "InvalidAmount")
		result = Decimal(str(value))
		_require(result.is_finite(), "InvalidAmount")
		return result
	except InvalidOperation:
		raise IncompleteBalance("InvalidAmount") from None


def _equal(left, right, reason="AllocationMismatch"):
	_require(abs(left - right) <= RECONCILIATION_TOLERANCE, reason)


def reconcile(contract, cutoff, data):
	"""Pure verification of a bounded canonical snapshot, not a second ledger."""
	try:
		settings, row = data["settings"], data["contract"]
		_require(row.get("name") == contract and row.get("docstatus") == 1 and row.get("status") in {"Active", "Suspended"}, "IneligibleContract")
		_require(settings.get("default_currency") == "HNL", "CurrencyUnavailable")
		for collection in ("debts", "items", "sources", "refinancings"):
			_require(all(r.get("currency", "HNL") in {None, "HNL"} for r in data[collection]), "CurrencyMismatch")
		debts = {r["name"]: r for r in data["debts"] if r["docstatus"] != 2}
		_require(all(len(data[k]) <= 5000 for k in ("debts", "items", "sources", "refinancings", "settled", "schedule")), "HistoryOutsideReadBound")
		_require(len({r["name"] for r in data["items"]}) == len(data["items"]), "DuplicateReceiptItem")
		_require(len(debts) == sum(r["docstatus"] != 2 for r in data["debts"]), "DuplicateLedger")
		sources = {(r["doctype"], r["name"]): r for r in data["sources"]}
		payments = {name: ZERO for name in debts}
		advances = {}
		gross = unused = ZERO
		for item in sorted(data["items"], key=lambda r: (cut_date(r["payment_date"]), str(r["payment_date"]), r["idx"], r["name"])):
			if item["docstatus"] != 1:
				continue
			_require(cut_date(item["payment_date"]) <= cutoff, "PaymentAfterCut")
			amount, balance = money(item["amount"]), money(item["balance"])
			_require(amount >= 0 and ZERO <= balance <= amount, "InvalidReceiptBalance")
			gross += amount
			unused += balance
			applied = amount - balance
			name = item.get("debt_ledger_entry")
			if name:
				_require(name in debts, "OrphanPayment")
				debt = debts[name]
				_require(item["payment_concept"] == debt["entry_type"], "ConceptMismatch")
				if debt["entry_type"] == "Monthly Fee":
					_require(item["billing_period"] == debt["billing_period"], "PeriodMismatch")
				payments[name] += applied
			else:
				_equal(applied, ZERO, "MissingAllocation")
			if balance > SETTLEMENT_TOLERANCE and item["payment_concept"] == "Monthly Fee":
				_require(bool(re.fullmatch(r"(?:0[1-9]|1[0-2])-[0-9]{4}", item.get("billing_period") or "")), "InvalidPeriod")
				advances.setdefault(item["billing_period"], []).append(balance)
		settled = {name: ZERO for name in debts}
		ref_credit = ZERO
		for ref in data["refinancings"]:
			if ref["docstatus"] != 1:
				continue
			_require(cut_date(ref["posting_date"]) <= cutoff, "SettlementAfterCut")
			rows = [s for s in data["settled"] if s["parent"] == ref["name"]]
			_require(bool(rows), "MissingSettlementLinks")
			total = ZERO
			for s in rows:
				name = s["debt_ledger_entry"]
				_require(name in debts and settled[name] == 0, "InvalidSettlement")
				amount = money(s["settled_amount"])
				_require(amount > SETTLEMENT_TOLERANCE and s["entry_type"] == debts[name]["entry_type"]
					and s["billing_period"] == debts[name]["billing_period"], "InvalidSettlement")
				settled[name] = amount
				total += amount
			_equal(total, money(ref["current_total_debt"]), "RefinancingMismatch")
			ref_credit += total
			new = [d for d in debts.values() if d["reference_doctype"] == "Debt Refinancing" and d["reference_name"] == ref["name"]]
			actual = sorted((cut_date(d["due_date"]), money(d["amount"])) for d in new if d["entry_type"] == "Refinancing Installment")
			expected = sorted((cut_date(s["due_date"]), money(s["amount"])) for s in data["schedule"] if s["parent"] == ref["name"])
			_require(actual == expected and bool(expected), "RefinancingScheduleMismatch")
			_equal(sum((money(d["amount"]) for d in new if d["entry_type"] == "Refinancing Down Payment"), ZERO), money(ref["down_payment"]), "RefinancingScheduleMismatch")
			_equal(sum((v for _, v in expected), ZERO) + money(ref["down_payment"]), total, "RefinancingScheduleMismatch")
		monthly_periods = set()
		totals = {k: ZERO for k in CONCEPTS}
		ledger_amount = outstanding_sum = advance_coverage = ZERO
		for name, d in debts.items():
			concept = d["entry_type"]
			_require(concept in CONCEPTS, "UnknownConcept")
			amount, paid, outstanding = (money(d[k]) for k in ("amount", "paid_amount", "outstanding_amount"))
			_require(amount > 0 and ZERO <= paid <= amount and outstanding >= 0, "InvalidLedgerAmount")
			_equal(amount - paid, outstanding, "OutstandingMismatch")
			_equal(payments[name] + settled[name], paid)
			status = "Paid" if outstanding <= SETTLEMENT_TOLERANCE else "Partially Paid" if paid > 0 else "Unpaid"
			_require(d["status"] == status, "LedgerStatusMismatch")
			_require(d.get("due_date") is not None, "MissingDueDate")
			due = cut_date(d["due_date"])
			ledger_amount += amount
			outstanding_sum += outstanding
			key = (d.get("reference_doctype"), d.get("reference_name"))
			expected_source = {"Monthly Fee": "Monthly Bill", "Service Fine": "Service Fine", "Connection Fee": "Connection Bill",
				"Reconnection Fee": "Service Reconnection", "Refinancing Down Payment": "Debt Refinancing", "Refinancing Installment": "Debt Refinancing"}.get(concept)
			if expected_source:
				_require(key[0] == expected_source, "MissingSource")
			if any(key):
				_require(key in sources, "MissingSource")
				source = sources[key]
				_require(source["docstatus"] == 1 and source["service_contract"] == contract, "InvalidSource")
				if concept in {"Monthly Fee", "Service Fine", "Connection Fee", "Reconnection Fee"}:
					_equal(amount, money(source["amount"]), "SourceAmountMismatch")
			if concept == "Monthly Fee":
				period = d.get("billing_period")
				_require(period not in monthly_periods and bool(re.fullmatch(r"(?:0[1-9]|1[0-2])-[0-9]{4}", period or "")), "DuplicateMonthlyPeriod")
				monthly_periods.add(period)
				source = sources[key]
				start, end = cut_date(source["start_date"]), cut_date(source["end_date"])
				_require(start < end and start.strftime("%m-%Y") == period and due >= end, "ContradictoryDates")
				_require(source["period"] == period, "PeriodMismatch")
			if due <= cutoff and outstanding > SETTLEMENT_TOLERANCE:
				remaining = outstanding
				if concept == "Monthly Fee":
					for balance in advances.get(d["billing_period"], []):
						if remaining <= SETTLEMENT_TOLERANCE:
							break
						remaining -= min(balance, remaining)
					advance_coverage += outstanding - remaining
				if remaining > SETTLEMENT_TOLERANCE:
					totals[concept] += remaining
		# Submitted sources must have corresponding ledger effects; empty ledger
		# cannot hide a submitted charge deleted outside its lifecycle.
		for source in data["sources"]:
			if source["docstatus"] != 1:
				continue
			if source["doctype"] in {"Monthly Bill", "Service Fine", "Connection Bill", "Service Reconnection"} and money(source["amount"]) > SETTLEMENT_TOLERANCE:
				_require(any(d["reference_doctype"] == source["doctype"] and d["reference_name"] == source["name"] for d in debts.values()), "MissingLedgerEffect")
		statement_net = sum((money(r["debit"]) - money(r["credit"]) for r in data["statement"]), ZERO)
		_equal(statement_net, ledger_amount - gross - ref_credit, "StatementMismatch")
		_equal(statement_net, outstanding_sum - unused, "StatementMismatch")
		additional = tuple((k, totals[k]) for k in sorted(ADDITIONAL) if totals[k] > ZERO)
		public_amounts = [totals[k] for k in ("Monthly Fee", "Service Fine", "Late Fee")] + [sum((v for _, v in additional), ZERO)]
		_require(sum((a.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for a in public_amounts), ZERO)
			== sum(public_amounts, ZERO).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "MonetaryProjectionMismatch")
		fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
		return BalanceResult("Verified", contract, cutoff, "HNL", totals["Monthly Fee"], totals["Service Fine"], totals["Late Fee"], additional=additional,
			total=sum(totals.values(), ZERO), ledger_count=len(debts), evidence_digest=fingerprint, statement_net=statement_net,
			ledger_amount=ledger_amount, receipt_amount=gross, unused_receipt_balance=unused, settlement_amount=ref_credit,
			monthly_advance_coverage=advance_coverage, ledger_references=tuple(sorted(debts)))
	except (IncompleteBalance, ValueError, TypeError, KeyError) as error:
		return BalanceResult("Unavailable", contract, cutoff, reason=getattr(error, "reason", "IncompleteSnapshot"))


def _permissions(contract):
	import frappe
	if frappe.session.user == "Guest":
		raise frappe.PermissionError(frappe._("Authentication required."))
	frappe.only_for("System Manager")
	for dt in ("Service Contract", "Billing Settings", "Debt Ledger Entry", "Payment Receipt", "Debt Refinancing",
		"Monthly Bill", "Service Fine", "Connection Bill", "Service Reconnection", "Billing Year"):
		frappe.has_permission(dt, "read", throw=True)
	frappe.get_doc("Service Contract", contract).check_permission("read")


def _rows(doctype, filters, fields, monetary_fields=()):
	"""Preserve MariaDB's nine decimals before legacy driver float conversion."""
	import frappe
	rows = frappe.get_all(doctype, filters=filters, fields=list(dict.fromkeys(["name", *fields])), limit_page_length=5001)
	_require(len(rows) <= 5000, "HistoryOutsideReadBound")
	if rows and monetary_fields:
		# Table/column identifiers come only from the fixed Billing schema below;
		# document names always remain query parameters.
		columns = ", ".join(f"CAST(`{field}` AS CHAR) AS `{field}`" for field in monetary_fields)
		values = frappe.db.sql(f"SELECT name, {columns} FROM `tab{doctype}` WHERE name IN %s",
			(tuple(r.name for r in rows),), as_dict=True)
		by_name = {r.name: r for r in values}
		for row in rows:
			row.update(by_name[row.name])
	return rows


def _load(contract, cutoff):
	import frappe
	from qota.billing.report.customer_statement import customer_statement as statement
	row = frappe.db.get_value("Service Contract", contract, ["name", "docstatus", "status", "start_date"], as_dict=True)
	settings = frappe.get_single("Billing Settings")
	_require(row and row.docstatus == 1 and row.status in {"Active", "Suspended"}, "IneligibleContract")
	debts = _rows("Debt Ledger Entry", {"service_contract": contract}, ["docstatus", "entry_type", "billing_period", "amount", "paid_amount", "outstanding_amount", "status", "due_date", "reference_doctype", "reference_name"], ("amount", "paid_amount", "outstanding_amount"))
	items = frappe.db.sql("""SELECT i.name, i.parent, i.idx, i.payment_concept, i.billing_period,
		CAST(i.amount AS CHAR) AS amount, CAST(i.balance AS CHAR) AS balance, i.debt_ledger_entry, p.payment_date, p.docstatus
		FROM `tabPayment Receipt Item` i JOIN `tabPayment Receipt` p ON p.name=i.parent
		WHERE p.service_contract=%s ORDER BY p.payment_date, i.idx, i.name LIMIT 5001""", (contract,), as_dict=True)
	refs = _rows("Debt Refinancing", {"service_contract": contract}, ["docstatus", "posting_date", "current_total_debt", "down_payment"], ("current_total_debt", "down_payment"))
	names = [r.name for r in refs]
	settled = _rows("Refinancing Settled Debt", {"parent": ["in", names]}, ["parent", "debt_ledger_entry", "entry_type", "billing_period", "settled_amount"], ("settled_amount",)) if names else []
	schedule = _rows("Amortization Schedule Item", {"parent": ["in", names]}, ["parent", "due_date", "amount"], ("amount",)) if names else []
	years = {r.name: r.year_name for r in frappe.get_all("Billing Year", fields=["name", "year_name"])}
	sources = []
	for dt, amount_field, extra in (("Monthly Bill", "grand_total", ["start_date", "end_date", "fiscal_month", "fiscal_year"]),
		("Service Fine", "amount", []), ("Connection Bill", "amount", []), ("Service Reconnection", "reconnection_fee", []), ("Debt Refinancing", "current_total_debt", [])):
		for source in _rows(dt, {"service_contract": contract}, ["docstatus", "service_contract", amount_field, *extra], (amount_field,)):
			source["doctype"], source["amount"] = dt, source[amount_field]
			if dt == "Monthly Bill":
				from calendar import month_name
				month = list(month_name).index(source.fiscal_month) if source.fiscal_month in month_name else 0
				source["period"] = f"{month:02d}-{years.get(source.fiscal_year, '')}"
			sources.append(source)
	_require(all(len(rows) <= 5000 for rows in (debts, items, refs, settled, schedule, sources)), "HistoryOutsideReadBound")
	# get_all is an internal bounded lookup, not a grant of row-level permissions.
	# Check every source and allocation document before projecting any amount.
	for dt, name in sorted({*(('Debt Ledger Entry', d.name) for d in debts), *(('Payment Receipt', i.parent) for i in items),
		*((s['doctype'], s.name) for s in sources)}):
		frappe.get_doc(dt, name).check_permission("read")
	return dict(contract=row or {}, settings={"default_currency": settings.get("default_currency")}, debts=debts, items=items,
		refinancings=refs, settled=settled, schedule=schedule, sources=sources,
		statement=statement._get_debt_rows(contract) + statement._get_payment_rows(contract) + statement._get_refinancing_rows(contract))


def read_balance(contract, cutoff=None):
	"""Internal, permission-checked read; no whitelist or Guest financial API."""
	import frappe
	if not isinstance(contract, str) or not re.fullmatch(r"SC-[0-9]{5}", contract):
		raise ValueError("Invalid contract identifier.")
	cutoff = cut_date(cutoff)
	try:
		_permissions(contract)
		return reconcile(contract, cutoff, _load(contract, cutoff))
	except frappe.PermissionError:
		raise
	except frappe.DoesNotExistError:
		return BalanceResult("Unavailable", contract, cutoff, reason="MissingDocument")
	except IncompleteBalance as error:
		return BalanceResult("Unavailable", contract, cutoff, reason=error.reason)
	except Exception as error:
		# Retry only connection loss/timeout, never snapshot serialization conflicts,
		# programming errors or missing schema. The caller retries the read transaction.
		transient = bool(error.args and isinstance(error.args[0], int) and error.args[0] in {2006, 2013, 2055}) or isinstance(error, (TimeoutError, ConnectionError))
		return BalanceResult("TechnicalFailure", contract, cutoff, reason="TransientReadFailure" if transient else "ReadFailure", transient=transient)
