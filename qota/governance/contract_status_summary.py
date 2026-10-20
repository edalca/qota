"""Authorized read-only contractual facts and independently verified order stages.

The caller owns the consistent snapshot. Current contract status is never
reconstructed from orders; an explicit date limits documentary stages only.
Diagnostics contain bounded codes and references, never reasons or amounts.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal

from qota.billing.balance_summary import (
	IncompleteBalance, RECONCILIATION_TOLERANCE, SETTLEMENT_TOLERANCE,
	_rows, cut_date, money,
)


@dataclass(frozen=True)
class OrderStage:
	availability: Literal["Verified", "Unavailable", "TechnicalFailure"] = "Verified"
	stage: Literal["Absent", "Scheduled", "Executed", "Cancelled", "PaymentPending", "ExecutionPending"] | None = "Absent"
	date: date | None = None
	reference: str | None = None
	reason: str | None = None

	def __post_init__(self):
		if self.availability not in {"Verified", "Unavailable", "TechnicalFailure"}:
			raise ValueError("Invalid stage availability.")
		if self.availability == "Verified":
			if self.stage not in {"Absent", "Scheduled", "Executed", "Cancelled", "PaymentPending", "ExecutionPending"} or self.reason:
				raise ValueError("Invalid verified stage.")
			if self.stage != "Absent" and not self.reference:
				raise ValueError("A stage requires documentary evidence.")
			if self.stage in {"Scheduled", "Executed"} and type(self.date) is not date:
				raise ValueError("A dated stage requires a date.")
			if self.stage == "Absent" and (self.reference or self.date):
				raise ValueError("An absent stage cannot contain evidence.")
		elif self.stage is not None or self.date is not None or not self.reason:
			raise ValueError("Unavailable stages cannot publish facts.")


@dataclass(frozen=True)
class StatusResult:
	status: Literal["Verified", "Unavailable", "TechnicalFailure"]
	contract: str
	cutoff: date
	canonical_status: Literal["Active", "Suspended"] | None = None
	suspension: OrderStage = OrderStage()
	reconnection: OrderStage = OrderStage()
	reason: str | None = None
	evidence_digest: str | None = None
	transient: bool = False

	def __post_init__(self):
		if not re.fullmatch(r"SC-[0-9]{5}", self.contract) or type(self.cutoff) is not date or type(self.transient) is not bool:
			raise ValueError("Invalid status identity.")
		if not isinstance(self.suspension, OrderStage) or not isinstance(self.reconnection, OrderStage):
			raise ValueError("Invalid order evidence.")
		if self.status == "Verified":
			if self.canonical_status not in {"Active", "Suspended"} or self.reason or not re.fullmatch(r"[0-9a-f]{64}", self.evidence_digest or ""):
				raise ValueError("A verified contract requires canonical evidence.")
			if self.suspension.stage not in {None, "Absent", "Scheduled", "Executed", "Cancelled"} or self.reconnection.stage not in {None, "Absent", "PaymentPending", "ExecutionPending", "Executed"}:
				raise ValueError("Invalid documentary stage kind.")
			if self.suspension.stage == "Scheduled" and self.canonical_status != "Active" or self.reconnection.stage == "Executed" and self.canonical_status != "Active":
				raise ValueError("Stage evidence conflicts with canonical status.")
		elif self.status not in {"Unavailable", "TechnicalFailure"} or not self.reason or self.canonical_status or self.evidence_digest or self.suspension != OrderStage() or self.reconnection != OrderStage():
			raise ValueError("Unavailable contracts cannot publish order facts.")

	def snapshot(self):
		value = asdict(self)
		value["cutoff"] = self.cutoff.isoformat()
		for key in ("suspension", "reconnection"):
			if value[key]["date"]:
				value[key]["date"] = value[key]["date"].isoformat()
		return value

	@classmethod
	def restore(cls, value):
		value = dict(value)
		value["cutoff"] = date.fromisoformat(value["cutoff"])
		for key in ("suspension", "reconnection"):
			stage = dict(value[key])
			if stage["date"]:
				stage["date"] = date.fromisoformat(stage["date"])
			value[key] = OrderStage(**stage)
		return cls(**value)


def _unavailable(reason, reference=None):
	return OrderStage("Unavailable", None, reference=reference, reason=reason)


def _day(value):
	return cut_date(value) if value else None


def _meter_evidence(order, data, field, day):
	if order.get("billing_basis") != "Metered":
		return True
	readings = [r for r in data.get("readings", ()) if r.get("docstatus") == 1 and _day(r.get("reading_date")) == day]
	return len(readings) == 1 and abs(money(readings[0].get("current_reading")) - money(order.get(field))) <= RECONCILIATION_TOLERANCE


def _chain(row, rows, contract):
	"""Only cancelled, same-contract ancestors prove amendment lineage."""
	seen = {row["name"]}
	while row.get("amended_from"):
		parent = rows.get(row["amended_from"])
		if not parent or parent["name"] in seen or parent.get("docstatus") != 2 or parent.get("service_contract") != contract:
			return False
		seen.add(parent["name"])
		row = parent
	return True


def _obligation(order, data, cutoff):
	"""Verify one canonical obligation, without calculating a contract balance."""
	fee = money(order.get("reconnection_fee"))
	if fee < 0:
		raise IncompleteBalance("InvalidObligation")
	debts = [d for d in data.get("debts", ()) if d.get("reference_name") == order["name"]]
	if fee == 0:
		if debts:
			raise IncompleteBalance("ZeroFeeObligationConflict")
		return "Settled"
	if len(debts) != 1:
		raise IncompleteBalance("MissingOrAmbiguousObligation")
	d = debts[0]
	if (d.get("docstatus") == 2 or d.get("entry_type") != "Reconnection Fee"
		or d.get("reference_doctype") != "Service Reconnection" or d.get("service_contract") != order["service_contract"]
		or not d.get("due_date") or _day(d["due_date"]) > cutoff):
		raise IncompleteBalance("InvalidObligation")
	amount, paid, outstanding = (money(d.get(k)) for k in ("amount", "paid_amount", "outstanding_amount"))
	if amount != fee or min(paid, outstanding) < 0 or abs(amount - paid - outstanding) > RECONCILIATION_TOLERANCE:
		raise IncompleteBalance("ObligationMismatch")
	if any(s.get("debt_ledger_entry") == d["name"] for s in data.get("settled", ())):
		raise IncompleteBalance("RefinancedObligation")
	applied = money(0)
	for item in data.get("items", ()):
		if item.get("debt_ledger_entry") != d["name"] or item.get("receipt_docstatus") != 1:
			continue
		if item.get("service_contract") != order["service_contract"] or item.get("payment_concept") != "Reconnection Fee" or not item.get("payment_date") or _day(item["payment_date"]) > cutoff:
			raise IncompleteBalance("InvalidPaymentEvidence")
		value, balance = money(item.get("amount")), money(item.get("balance"))
		if balance < 0 or value < balance:
			raise IncompleteBalance("InvalidPaymentEvidence")
		applied += value - balance
	if abs(applied - paid) > RECONCILIATION_TOLERANCE:
		raise IncompleteBalance("PaymentEvidenceMismatch")
	expected = "Paid" if outstanding <= SETTLEMENT_TOLERANCE else "Partially Paid" if paid > 0 else "Unpaid"
	if d.get("status") != expected:
		raise IncompleteBalance("ObligationStatusMismatch")
	return "Settled" if expected == "Paid" else "Pending"


def summarize(contract, cutoff, data, historical_suspension=None):
	"""Pure minimal projection. Documentary failures never replace contract status."""
	cutoff = cut_date(cutoff)
	row = data["contract"]
	if row.get("name") != contract or row.get("docstatus") != 1 or row.get("status") not in {"Active", "Suspended"}:
		return StatusResult("Unavailable", contract, cutoff, reason="IneligibleContract")
	suspensions = {s["name"]: s for s in data.get("suspensions", ())}
	reconnections = {r["name"]: r for r in data.get("reconnections", ())}
	active_s = [s for s in suspensions.values() if s.get("docstatus") == 1]
	scheduled = [s for s in active_s if s.get("status") == "Scheduled"]
	suspension = OrderStage()
	if historical_suspension:
		old = suspensions.get(historical_suspension)
		if old and old.get("docstatus") == 2 and _chain(old, suspensions, contract):
			suspension = OrderStage(stage="Cancelled", reference=old["name"])
		else:
			suspension = _unavailable("HistoricalReferenceUnverified")
	elif any(not _chain(s, suspensions, contract) for s in active_s) or len(scheduled) > 1:
		suspension = _unavailable("AmbiguousSuspension")
	elif scheduled:
		s = scheduled[0]
		if s.get("service_contract") != contract or not s.get("effective_date") or s.get("executed_date") or row["status"] != "Active":
			suspension = _unavailable("SuspensionEvidenceMismatch", s["name"])
		else:
			suspension = OrderStage(stage="Scheduled", date=_day(s["effective_date"]), reference=s["name"])
	current_s = [s for s in active_s if s.get("status") == "Executed" and s.get("service_contract") == contract
		and s.get("effective_date") and _day(s["effective_date"]) == _day(row.get("suspended_since"))
		and s.get("executed_date") and _day(s["executed_date"]) <= cutoff and _chain(s, suspensions, contract)]
	if not historical_suspension and not scheduled and row["status"] == "Suspended" and current_s:
		if len(current_s) == 1:
			s = current_s[0]
			if _meter_evidence(s, data, "final_reading", _day(s["executed_date"])):
				suspension = OrderStage(stage="Executed", date=_day(s["executed_date"]), reference=s["name"])
			else:
				suspension = _unavailable("MeterReadingEvidenceUnavailable", s["name"])
		else:
			suspension = _unavailable("AmbiguousSuspension")
	if not historical_suspension and any(s.get("status") not in {"Scheduled", "Executed"} or s.get("status") == "Executed" and not s.get("executed_date") for s in active_s):
		suspension = _unavailable("SuspensionEvidenceMismatch")
	if not historical_suspension and any(not _chain(s, suspensions, contract) for s in active_s):
		suspension = _unavailable("AmbiguousSuspension")
	if not historical_suspension and row["status"] == "Suspended" and active_s and not scheduled and not current_s:
		suspension = _unavailable("CurrentSuspensionUnverified")
	active_r = [r for r in reconnections.values() if r.get("docstatus") == 1]
	# A completed old cycle is not current solely because it was created later.
	candidates = [r for r in active_r if r.get("service_suspension") in {s["name"] for s in current_s}
		or not r.get("execution_date") or r.get("execution_date") and _day(r["execution_date"]) == _day(row.get("reactivation_date"))]
	reconnection = OrderStage()
	if any(r.get("service_contract") != contract or not _chain(r, reconnections, contract) for r in active_r):
		reconnection = _unavailable("ReconnectionRelationshipMismatch")
	elif len(candidates) > 1:
		reconnection = _unavailable("AmbiguousReconnection")
	elif candidates:
		r = candidates[0]
		s = suspensions.get(r.get("service_suspension"))
		if len(current_s) != 1 or s is not current_s[0]:
			reconnection = _unavailable("ReconnectionRelationshipMismatch", r["name"])
		elif r.get("status") == "Scheduled":
			# The installed model has neither a scheduling producer nor a date.
			reconnection = _unavailable("SchedulingEvidenceUnavailable", r["name"])
		else:
			try:
				obligation = _obligation(r, data, cutoff)
				if r.get("status") == "Executed":
					day = _day(r.get("execution_date"))
					if (not day or day > cutoff or day < _day(s["executed_date"]) or row["status"] != "Active"
						or _day(row.get("reactivation_date")) != day or obligation != "Settled"
						or not _meter_evidence(r, data, "initial_reading", day)):
						reconnection = _unavailable("ExecutionEvidenceMismatch", r["name"])
					else:
						reconnection = OrderStage(stage="Executed", date=day, reference=r["name"])
				elif r.get("execution_date") or row["status"] != "Suspended":
					reconnection = _unavailable("ReconnectionEvidenceMismatch", r["name"])
				elif r.get("status") == "Unpaid" and obligation == "Pending":
					reconnection = OrderStage(stage="PaymentPending", reference=r["name"])
				elif r.get("status") == "Paid" and obligation == "Settled":
					reconnection = OrderStage(stage="ExecutionPending", reference=r["name"])
				else:
					reconnection = _unavailable("ReconnectionObligationMismatch", r["name"])
			except IncompleteBalance as error:
				reconnection = _unavailable(error.reason, r["name"])
	if not historical_suspension and row["status"] == "Active" and current_s and not scheduled and reconnection.stage != "Executed":
		suspension = _unavailable("SuspensionContractMismatch")
	value = dict(contract=contract, cutoff=cutoff.isoformat(), canonical_status=row["status"],
		suspension=asdict(suspension), reconnection=asdict(reconnection))
	digest = hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
	return StatusResult("Verified", contract, cutoff, row["status"], suspension, reconnection, evidence_digest=digest)


def _permissions(doctype, names=()):
	import frappe
	frappe.has_permission(doctype, "read", throw=True)
	for name in names:
		frappe.get_doc(doctype, name).check_permission("read")


def _load_orders(contract):
	import frappe
	_permissions("Service Suspension")
	_permissions("Service Reconnection")
	suspensions = frappe.get_all("Service Suspension", filters={"service_contract": contract},
		fields=["name", "service_contract", "docstatus", "status", "effective_date", "executed_date", "amended_from", "billing_basis", "final_reading"], limit_page_length=201)
	names = [s.name for s in suspensions]
	scope = {"or_filters": {"service_contract": contract, "service_suspension": ["in", names]}} if names else {"filters": {"service_contract": contract}}
	reconnections = frappe.get_all("Service Reconnection", **scope,
		fields=["name", "service_contract", "service_suspension", "docstatus", "status", "execution_date", "amended_from", "billing_basis", "initial_reading"], limit_page_length=201)
	if len(suspensions) > 200 or len(reconnections) > 200:
		raise IncompleteBalance("OrderReadBoundExceeded")
	_permissions("Service Suspension", names)
	_permissions("Service Reconnection", [r.name for r in reconnections])
	reading_days = {s.executed_date for s in suspensions if s.executed_date and s.billing_basis == "Metered"}
	reading_days.update(r.execution_date for r in reconnections if r.execution_date and r.billing_basis == "Metered")
	readings = []
	if reading_days:
		_permissions("Meter Reading")
		readings = frappe.get_all("Meter Reading", filters={"service_contract": contract, "reading_date": ["in", list(reading_days)]},
			fields=["name", "docstatus", "reading_date", "current_reading"], limit_page_length=201)
		if len(readings) > 200:
			raise IncompleteBalance("OrderReadBoundExceeded")
		_permissions("Meter Reading", [r.name for r in readings])
	return dict(suspensions=suspensions, reconnections=reconnections, readings=readings)


def _load_obligations(orders):
	import frappe
	names = [r["name"] for r in orders["reconnections"] if r["docstatus"] == 1]
	if not names:
		return
	# Child-table access derives from its permission-checked parent document.
	for dt in ("Debt Ledger Entry", "Payment Receipt", "Debt Refinancing"):
		_permissions(dt)
	fees = _rows("Service Reconnection", {"name": ["in", names]}, ["reconnection_fee"], ("reconnection_fee",))
	for r in orders["reconnections"]:
		if r["name"] in names:
			r["reconnection_fee"] = next(f.reconnection_fee for f in fees if f.name == r["name"])
	debts = _rows("Debt Ledger Entry", {"reference_doctype": "Service Reconnection", "reference_name": ["in", names]},
		["docstatus", "service_contract", "entry_type", "reference_doctype", "reference_name", "due_date", "status", "amount", "paid_amount", "outstanding_amount"],
		("amount", "paid_amount", "outstanding_amount"))
	debt_names = [d.name for d in debts]
	items = frappe.db.sql("""SELECT i.name, i.parent, i.debt_ledger_entry, i.payment_concept,
		CAST(i.amount AS CHAR) AS amount, CAST(i.balance AS CHAR) AS balance,
		p.docstatus AS receipt_docstatus, p.payment_date, p.service_contract
		FROM `tabPayment Receipt Item` i JOIN `tabPayment Receipt` p ON p.name=i.parent
		WHERE i.debt_ledger_entry IN %s LIMIT 5001""", (tuple(debt_names),), as_dict=True) if debt_names else []
	settled = frappe.get_all("Refinancing Settled Debt", filters={"debt_ledger_entry": ["in", debt_names]},
		fields=["parent", "debt_ledger_entry"], limit_page_length=5001) if debt_names else []
	if max(len(debts), len(items), len(settled)) > 5000:
		raise IncompleteBalance("ObligationReadBoundExceeded")
	_permissions("Debt Ledger Entry", debt_names)
	_permissions("Payment Receipt", {i.parent for i in items})
	_permissions("Debt Refinancing", {s.parent for s in settled})
	orders.update(debts=debts, items=items, settled=settled)


def read_status(contract, cutoff=None, *, historical_suspension=None):
	"""Internal System Manager read; no public endpoint or arbitrary order lookup."""
	import frappe
	if not isinstance(contract, str) or not re.fullmatch(r"SC-[0-9]{5}", contract):
		raise ValueError("Invalid contract identifier.")
	cutoff = cut_date(cutoff)
	if frappe.session.user == "Guest" or "System Manager" not in frappe.get_roles():
		raise frappe.PermissionError("System Manager is required.")
	try:
		_permissions("Service Contract", (contract,))
		row = frappe.db.get_value("Service Contract", contract, ["name", "docstatus", "status", "suspended_since", "reactivation_date"], as_dict=True)
		if not row or row.docstatus != 1 or row.status not in {"Active", "Suspended"}:
			return StatusResult("Unavailable", contract, cutoff, reason="IneligibleContract")
		try:
			orders = _load_orders(contract)
			try:
				_load_obligations(orders)
			except frappe.PermissionError:
				raise
			except Exception as error:
				base = summarize(contract, cutoff, dict(contract=row, **orders), historical_suspension)
				stage = _unavailable(error.reason) if isinstance(error, IncompleteBalance) else OrderStage("TechnicalFailure", None, reason="TransientReadFailure" if _transient(error) else "ObligationReadFailure")
				from dataclasses import replace
				return replace(base, reconnection=stage, transient=_transient(error), evidence_digest=hashlib.sha256(json.dumps([base.snapshot(), stage.reason], sort_keys=True).encode()).hexdigest())
			return summarize(contract, cutoff, dict(contract=row, **orders), historical_suspension)
		except frappe.PermissionError:
			raise
		except Exception as error:
			transient = _transient(error)
			stage = _unavailable(error.reason) if isinstance(error, IncompleteBalance) else OrderStage("TechnicalFailure", None, reason="TransientReadFailure" if transient else "OrderReadFailure")
			# Preserve independently verified contractual authority even when all
			# extra documentary facts are unavailable. No exception text escapes.
			digest = hashlib.sha256(f"{contract}:{cutoff}:{row.status}:{stage.reason}".encode()).hexdigest()
			return StatusResult("Verified", contract, cutoff, row.status, stage, stage, evidence_digest=digest, transient=transient)
	except frappe.PermissionError:
		raise
	except frappe.DoesNotExistError:
		return StatusResult("Unavailable", contract, cutoff, reason="MissingDocument")
	except Exception as error:
		return StatusResult("TechnicalFailure", contract, cutoff, reason="TransientReadFailure" if _transient(error) else "ReadFailure", transient=_transient(error))


def _transient(error):
	return isinstance(error, (TimeoutError, ConnectionError)) or bool(error.args and isinstance(error.args[0], int) and error.args[0] in {2006, 2013, 2055})
