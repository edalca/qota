"""Recover settlement provenance only from a uniquely attributable legacy liquidation."""

from decimal import Decimal

import frappe
from frappe.model.naming import set_new_name
from frappe.modules.patch_handler import PatchError

from qota.migration_identity import historical_completion

TOLERANCE = Decimal("0.01")


def money(value):
    return Decimal(str(value or 0))


def require(condition, code, name):
    if not condition:
        raise PatchError(f"{code}: {name}")


def execute():
    if historical_completion("qota.patches.record_refinanced_debts"):
        return
    _migrate()


def _migrate():
    refs = frappe.get_all("Debt Refinancing", filters={"docstatus": 1},
        fields=["name", "service_contract", "current_total_debt"], order_by="name")
    plans = []
    for ref in refs:
        existing = frappe.get_all("Refinancing Settled Debt", filters={"parent": ref.name}, fields=["*"])
        if existing:
            _validate_existing(ref, existing)
            continue
        require(frappe.db.count("Debt Refinancing", {"service_contract": ref.service_contract}) == 1,
            "RefinancingAttributionAmbiguous", ref.name)
        plans.append((ref, _plan(ref)))
    # All contracts are checked before inserting any relationship. The Frappe
    # patch transaction owns commit/rollback, including failure during insertion.
    for ref, debts in plans:
        for idx, (debt, settled) in enumerate(debts, 1):
            row = frappe.new_doc("Refinancing Settled Debt")
            row.update(dict(parent=ref.name, parentfield="settled_debts", parenttype="Debt Refinancing",
                idx=idx, debt_ledger_entry=debt.name, entry_type=debt.entry_type,
                billing_period=debt.billing_period, settled_amount=settled,
                reference_doctype=debt.reference_doctype, reference_name=debt.reference_name))
            set_new_name(row)
            row.db_insert()


def _validate_existing(ref, rows):
    seen = set()
    total = Decimal(0)
    for row in rows:
        debt = frappe.db.get_value("Debt Ledger Entry", row.debt_ledger_entry,
            ["service_contract", "entry_type", "billing_period", "amount", "reference_doctype", "reference_name", "docstatus"], as_dict=True)
        require(debt and debt.docstatus != 2 and debt.service_contract == ref.service_contract
            and row.parenttype == "Debt Refinancing" and row.parentfield == "settled_debts"
            and row.debt_ledger_entry not in seen and money(row.settled_amount) > TOLERANCE
            and money(row.settled_amount) <= money(debt.amount)
            and all((row.get(k) or "") == (debt.get(k) or "")
                for k in ("entry_type", "billing_period", "reference_doctype", "reference_name")),
            "RefinancingLinksInvalid", ref.name)
        require(frappe.db.count("Refinancing Settled Debt", {"debt_ledger_entry": row.debt_ledger_entry}) == 1,
            "RefinancingDebtAlreadyAttributed", row.debt_ledger_entry)
        seen.add(row.debt_ledger_entry)
        total += money(row.settled_amount)
    require(abs(total - money(ref.current_total_debt)) <= TOLERANCE,
        "RefinancingLinksIncomplete", ref.name)


def _plan(ref):
    # on_submit generated these obligations only after settling the original
    # debts. Their earliest creation is documentary evidence of that boundary;
    # the parent's mutable modified timestamp is deliberately never consulted.
    generated = frappe.db.sql("SELECT MIN(creation),SUM(amount) FROM `tabDebt Ledger Entry` "
        "WHERE reference_doctype='Debt Refinancing' AND reference_name=%s AND service_contract=%s "
        "AND docstatus!=2 AND entry_type IN ('Refinancing Down Payment','Refinancing Installment')",
        (ref.name, ref.service_contract))[0]
    cutoff, financed = generated
    require(cutoff and abs(money(financed) - money(ref.current_total_debt)) <= TOLERANCE
        and money(ref.current_total_debt) > TOLERANCE, "RefinancingSubmissionEvidenceMissing", ref.name)
    debts = frappe.db.sql("""
        SELECT dle.name,dle.entry_type,dle.billing_period,dle.reference_doctype,dle.reference_name,
            CAST(dle.amount AS CHAR) AS amount,CAST(dle.paid_amount AS CHAR) AS paid_amount,
            CAST(dle.outstanding_amount AS CHAR) AS outstanding_amount,dle.status,
            CAST(COALESCE(SUM(CASE WHEN pr.name IS NOT NULL THEN pri.amount-pri.balance ELSE 0 END),0) AS CHAR) AS applied,
            SUM(CASE WHEN pr.name IS NOT NULL AND (pri.creation >= %(cutoff)s OR pri.balance < 0
                OR pri.balance > pri.amount) AND pri.amount-pri.balance != 0 THEN 1 ELSE 0 END) AS unsafe_payments
        FROM `tabDebt Ledger Entry` dle
        LEFT JOIN `tabPayment Receipt Item` pri ON pri.debt_ledger_entry=dle.name
        LEFT JOIN `tabPayment Receipt` pr ON pr.name=pri.parent AND pr.docstatus=1
        WHERE dle.service_contract=%(contract)s AND dle.creation < %(cutoff)s AND dle.docstatus!=2
            AND dle.entry_type NOT IN ('Refinancing Down Payment','Refinancing Installment')
        GROUP BY dle.name ORDER BY dle.name
    """, dict(contract=ref.service_contract, cutoff=cutoff), as_dict=True)
    plan = []
    for debt in debts:
        settled = money(debt.paid_amount) - money(debt.applied)
        require(settled >= -TOLERANCE, "RefinancingPaymentMismatch", debt.name)
        if settled <= TOLERANCE:
            continue
        require(not debt.unsafe_payments and debt.status == "Paid"
            and abs(money(debt.outstanding_amount)) <= TOLERANCE
            and abs(money(debt.amount) - money(debt.paid_amount)) <= TOLERANCE
            and money(debt.applied) >= 0 and settled <= money(debt.amount),
            "RefinancingSettlementUnproven", debt.name)
        require(not frappe.db.exists("Refinancing Settled Debt", {"debt_ledger_entry": debt.name}),
            "RefinancingDebtAlreadyAttributed", debt.name)
        plan.append((debt, settled))
    require(plan and abs(sum((s for _, s in plan), Decimal(0)) - money(ref.current_total_debt)) <= TOLERANCE,
        "RefinancingTotalMismatch", ref.name)
    return plan
