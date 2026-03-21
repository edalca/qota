# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt


from datetime import date
from typing import TYPE_CHECKING

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, get_last_day, getdate, today

if TYPE_CHECKING:
	from qota.billing.doctype.billing_settings.billing_settings import BillingSettings
	from qota.billing.doctype.service_rate.service_rate import ServiceRate
	from qota.governance.doctype.service_contract.service_contract import ServiceContract


@frappe.whitelist()
def get_monthly_billing_breakdown(contract_name, billing_month, billing_year, start_date, end_date):
	"""
	Core Billing Engine.
	Adjusts billing days based on the Service Contract's actual start date
	and month-specific duration.
	"""
	contract = frappe.get_doc("Service Contract", contract_name)
	settings = frappe.get_doc("Billing Settings")

	period_start = getdate(start_date)
	contract_start = getdate(contract.start_date)

	actual_billing_start = max(period_start, contract_start)

	if actual_billing_start > getdate(end_date):
		return {"total_to_bill": 0.0, "detailed_items": [], "total_days": 0}

	last_day_of_month = get_last_day(actual_billing_start)
	days_in_this_month = getdate(last_day_of_month).day

	total_days = date_diff(end_date, actual_billing_start) + 1

	if total_days >= days_in_this_month:
		proration_factor = 1.0
	else:
		proration_factor = flt(total_days) / flt(days_in_this_month)

	service_rate = get_active_service_rate(contract, end_date)

	# TODO: Proration rule not yet defined by the board.
	# Standard formula (days / days_in_month) is calculated above but
	# intentionally overridden to 1 until the policy is confirmed.
	# Remove this line once the proration policy is established.
	proration_factor = 1

	if service_rate.billing_basis == "Flat Rate":
		base_results = calculate_flat_rate(contract, service_rate, settings, proration_factor, total_days)

	elif service_rate.billing_basis == "Metered":
		base_results = calculate_metered_rate(
			contract, service_rate, settings, actual_billing_start, end_date, proration_factor, total_days
		)

	else:
		frappe.throw(_("Invalid Billing Basis for contract {0}").format(contract_name))

	additional_fee = calculate_additional_fee(service_rate)

	base_results["discountable_amount"] += additional_fee["discountable_amount"]
	base_results["non_discountable_amount"] += additional_fee["non_discountable_amount"]
	base_results["detailed_items"].extend(additional_fee["detailed_items"])

	discount_logic = apply_discount_logic(contract, settings, end_date)

	final_breakdown = finalize_breakdown(
		base_results,
		discount_logic["total_pct"],
		discount_logic["total_fixed"],
		discount_logic["selected_rules"],
	)

	final_breakdown.update(
		{
			"billing_month": billing_month,
			"billing_year": billing_year,
			"total_days": total_days,
			"actual_start": actual_billing_start,
		}
	)

	return final_breakdown


def get_active_service_rate(contract: "ServiceContract", reference_date: str | date) -> "ServiceRate":
	rate_name = frappe.db.get_value(
		"Service Rate",
		{
			"service_category": contract.service_category,
			"billing_basis": contract.billing_basis,
			"status": "Active",
			"effective_from": ["<=", reference_date],
		},
		"name",
		order_by="effective_from desc",
	)

	if not rate_name:
		frappe.throw(
			_("No active Service Rate found for category '{0}' on {1}").format(
				contract.service_category, reference_date
			)
		)

	return frappe.get_doc("Service Rate", rate_name)


def calculate_flat_rate(
	contract: "ServiceContract",
	service_rate: "ServiceRate",
	settings: "BillingSettings",
	factor: float,
	days: int,
):
	"""Calculates Flat Rate with optional pro-rating."""
	base_price = flt(service_rate.flat_rate_price or 0) * factor
	cistern_fee = (flt(service_rate.cistern_fee or 0) * factor) if contract.has_cistern else 0
	detailed_items = []

	suffix = f" ({days} days)" if factor < 1.0 else ""

	if settings.separate_cistern_fee:
		detailed_items.append(
			{
				"description": ("{0} ({1} - {2})").format(
					settings.water_service_label, _("Flat Rate"), service_rate.rate_name
				)
				+ suffix,
				"amount": base_price,
			}
		)
		if cistern_fee > 0:
			detailed_items.append({"description": _("Cistern Fee") + suffix, "amount": cistern_fee})
	else:
		detailed_items.append(
			{
				"description": ("{0} ({1})").format(settings.water_service_label, _("Flat Rate")) + suffix,
				"amount": base_price + cistern_fee,
			}
		)

	category_allows = frappe.db.get_value(
		"Service Category", service_rate.service_category, "allow_discounts"
	)

	discountable_sum = (base_price + cistern_fee) if category_allows else 0
	non_discountable_sum = 0 if category_allows else (base_price + cistern_fee)

	return {
		"discountable_amount": discountable_sum,
		"non_discountable_amount": non_discountable_sum,
		"base_rate": base_price,
		"cistern_fee": cistern_fee,
		"detailed_items": detailed_items,
	}


def calculate_metered_rate(
	contract: "ServiceContract",
	service_rate: "ServiceRate",
	settings: "BillingSettings",
	start_date: str | date,
	end_date: str | date,
	factor: float,
	days: int,
):
	"""Calculates Metered charges using date range for readings."""
	fixed_charge = flt(service_rate.fixed_charge or 0) * factor
	min_m3 = flt(service_rate.min_consumption or 0)
	detailed_items = []

	suffix = f" ({days} days)" if factor < 1.0 else ""
	detailed_items.append(
		{"description": _("Fixed Charge (Up to {0} m3)").format(min_m3) + suffix, "amount": fixed_charge}
	)

	reading_data = frappe.db.sql(
		"""
        SELECT consumption FROM `tabMeter Reading`
        WHERE service_contract = %s AND reading_date BETWEEN %s AND %s AND docstatus = 1
        ORDER BY reading_date DESC LIMIT 1
    """,
		(contract.name, start_date, end_date),
		as_dict=True,
	)

	total_consumption = flt(reading_data[0].consumption) if reading_data else 0
	excess_m3 = max(0, total_consumption - min_m3)
	excess_amount = 0.0

	if excess_m3 > 0:
		tiers = service_rate.get("consumption_tiers") or []
		remaining_excess = excess_m3
		prev_limit = min_m3
		for tier in tiers:
			if remaining_excess <= 0:
				break

			t_limit = flt(tier.up_to_m3)
			t_size = (t_limit - prev_limit) if t_limit > 0 else remaining_excess
			m3_tier = min(remaining_excess, t_size)
			cost = m3_tier * flt(tier.price_per_m3)
			if m3_tier > 0:
				detailed_items.append(
					{
						"description": _("Excess: {0} m3 at {1}/m3").format(m3_tier, tier.price_per_m3),
						"amount": cost,
					}
				)
				excess_amount += cost
			remaining_excess -= m3_tier
			prev_limit = t_limit

	category_allows = frappe.db.get_value(
		"Service Category", service_rate.service_category, "allow_discounts"
	)
	total_base = fixed_charge + excess_amount
	discountable_sum = total_base if category_allows else 0
	non_discountable_sum = 0 if category_allows else total_base

	return {
		"discountable_amount": discountable_sum,
		"non_discountable_amount": non_discountable_sum,
		"base_rate": fixed_charge,
		"excess_amount": excess_amount,
		"detailed_items": detailed_items,
	}


def calculate_additional_fee(
	service_rate: "ServiceRate",
):
	discountable_sum = 0
	non_discountable_sum = 0
	detailed_items = []

	for fee in service_rate.get("additional_fees") or []:
		fee_amt = flt(fee.amount)
		detailed_items.append({"description": fee.description or _("Additional Fee"), "amount": fee_amt})
		if flt(fee.allow_discounts):
			discountable_sum += fee_amt
		else:
			non_discountable_sum += fee_amt
	return {
		"discountable_amount": discountable_sum,
		"non_discountable_amount": non_discountable_sum,
		"detailed_items": detailed_items,
	}


def apply_discount_logic(
	contract: "ServiceContract", settings: "BillingSettings", reference_date: str | date
):
	"""
	Evaluates discount rules based on age and cistern requirements.
	Supports both Fixed Amount and Percentage discounts.
	"""
	subscriber = frappe.get_doc("Subscriber", contract.subscriber)

	if getattr(subscriber, "subscriber_type", "Natural Person") == "Juridical Person":
		return {"total_pct": 0, "total_fixed": 0, "selected_rules": []}

	cistern_filter = ["Irrelevant"]
	cistern_filter.append("Yes" if contract.has_cistern else "No")

	applicable_rules = []

	if subscriber.birth_date:
		age = int(date_diff(reference_date, subscriber.birth_date) / 365.25)

		age_rules = frappe.get_all(
			"Discount Rule",
			filters={
				"condition_type": "Age",
				"minimum_age": ["<=", age],
				"requires_cistern": ["in", cistern_filter],
				"is_active": 1,
			},
			fields=["name", "discount_type", "discount_percentage", "fixed_amount", "maximum_age"],
		)

		for r in age_rules:
			if r.maximum_age == 0 or age <= r.maximum_age:
				applicable_rules.append(r)

	benefits = frappe.get_all(
		"Benefit Discount",
		filters={
			"service_contract": contract.name,
			"status": "Active",
			"effective_date": ["<=", reference_date],
		},
		fields=["discount_rule"],
	)

	for b in benefits:
		rule = frappe.db.get_value(
			"Discount Rule",
			b.discount_rule,
			["name", "discount_type", "discount_percentage", "fixed_amount"],
			as_dict=True,
		)

		if rule:
			applicable_rules.append(rule)

	applicable_rules.sort(key=lambda x: flt(x.fixed_amount) or flt(x.discount_percentage), reverse=True)

	max_rules = settings.max_discounts_per_subscriber or 1
	selected_rules = applicable_rules[:max_rules]

	total_pct = sum(flt(r.discount_percentage) for r in selected_rules if r.discount_type == "Percentage")
	total_fixed = sum(flt(r.fixed_amount) for r in selected_rules if r.discount_type == "Fixed Amount")

	return {"total_pct": min(total_pct, 100.0), "total_fixed": total_fixed, "selected_rules": selected_rules}


def finalize_breakdown(base_results, discount_pct, total_fixed, rules):
	"""
	Finalizes bill calculation applying both Percentage and Fixed discounts.
	"""
	settings = frappe.get_single("Billing Settings")

	discountable = flt(base_results["discountable_amount"])
	non_discountable = flt(base_results["non_discountable_amount"])

	pct_discount = flt(discountable * (discount_pct / 100))

	total_discount_amount = pct_discount + flt(total_fixed)

	if total_discount_amount > discountable:
		total_discount_amount = discountable

	if settings.truncate_discount_decimals:
		total_discount_amount = int(total_discount_amount)

	total_to_bill = (discountable + non_discountable) - total_discount_amount

	if settings.truncate_discount_decimals:
		total_to_bill = int(total_to_bill)

	items = base_results.get("detailed_items", [])

	if total_discount_amount > 0:
		rule_list = ", ".join([r.name for r in rules])
		items.append(
			{"description": _("Applied Discounts ({0})").format(rule_list), "amount": -total_discount_amount}
		)

	return {
		"total_to_bill": flt(total_to_bill),
		"detailed_items": items,
		"discount_amount": total_discount_amount,
		"discount_percentage": discount_pct,
		"fixed_discount_applied": total_fixed,
		"base_rate": base_results.get("base_rate", 0),
		"cistern_fee": base_results.get("cistern_fee", 0),
	}


@frappe.whitelist()
def get_billing_gaps():
	"""
	Identifies contracts missed during completed Billing Cycles.
	Respects activity gaps (reactivation_date) and
	suspension periods (suspended_since).
	"""
	from frappe.utils import getdate

	open_years = frappe.get_all("Billing Year", filters={"is_closed": 0}, pluck="name")
	if not open_years:
		return []

	completed_cycles = frappe.get_all(
		"Billing Cycle",
		filters={"status": "Completed", "fiscal_year": ["in", open_years], "docstatus": 1},
		fields=["fiscal_year", "fiscal_month", "start_date", "end_date"],
	)
	if not completed_cycles:
		return []

	contracts = frappe.get_all(
		"Service Contract",
		filters={"status": ["in", ["Active", "Suspended"]], "docstatus": 1},
		fields=["name", "full_name", "start_date", "reactivation_date", "suspended_since", "status"],
	)

	existing_bills = frappe.get_all(
		"Monthly Bill",
		filters={"fiscal_year": ["in", open_years], "docstatus": ["!=", 2]},
		fields=["service_contract", "fiscal_year", "fiscal_month"],
	)
	billed_lookup = {(b.service_contract, b.fiscal_year, b.fiscal_month) for b in existing_bills}

	gaps = []

	for cycle in completed_cycles:
		c_start = getdate(cycle.start_date)
		c_end = getdate(cycle.end_date)

		for c in contracts:
			start = getdate(c.start_date)
			reactivation = getdate(c.reactivation_date) if c.reactivation_date else start

			effective_start = max(start, reactivation)

			if c.status == "Suspended" and c.suspended_since:
				if getdate(c.suspended_since) <= c_start:
					continue

			if effective_start <= c_end:
				if (c.name, cycle.fiscal_year, cycle.fiscal_month) not in billed_lookup:
					gaps.append(
						{
							"contract": c.name,
							"full_name": c.full_name,
							"year": cycle.fiscal_year,
							"month": cycle.fiscal_month,
							"period": _("{0} {1}").format(_(cycle.fiscal_month), cycle.fiscal_year),
						}
					)

	return gaps


@frappe.whitelist()
def generate_bills_and_link_advances(gap_list):
	"""
	Generate monthly bills for specific gaps.

	The submission of the bill automatically triggers the creation
	of the debt ledger entry and the application of any existing
	advance payments for that period.
	"""
	import json
	from datetime import date

	from frappe.utils import add_months

	if isinstance(gap_list, str):
		gap_list = json.loads(gap_list)

	settings = frappe.get_single("Billing Settings")
	start_day = int(settings.cycle_start_day or 1)
	month_map = {
		"January": 1,
		"February": 2,
		"March": 3,
		"April": 4,
		"May": 5,
		"June": 6,
		"July": 7,
		"August": 8,
		"September": 9,
		"October": 10,
		"November": 11,
		"December": 12,
	}

	success_count = 0
	for gap in gap_list:
		try:
			contract_id = gap.get("contract")
			fiscal_year = int(gap.get("year"))
			fiscal_month = gap.get("month")
			m_num = month_map[fiscal_month]

			s_start = date(fiscal_year, m_num, start_day)
			s_end = add_days(add_months(s_start, 1), -1)

			bill = frappe.new_doc("Monthly Bill")
			bill.service_contract = contract_id
			bill.fiscal_year = gap.get("year")
			bill.fiscal_month = fiscal_month
			bill.start_date = s_start
			bill.end_date = s_end
			bill.posting_date = today()
			bill.insert()
			bill.submit()

			success_count += 1
		except Exception as e:
			frappe.log_error(f"Gap Error {contract_id}: {e!s}", "Billing")

	return _("Successfully generated {0} bills.").format(success_count)


def update_dle_totals(dle_name):
	"""Calculates paid and outstanding amounts for the Ledger Entry."""
	total_paid = (
		frappe.db.sql(
			"""
        SELECT SUM(amount) FROM `tabPayment Receipt Item` WHERE debt_ledger_entry = %s
    """,
			dle_name,
		)[0][0]
		or 0
	)

	amount = frappe.db.get_value("Debt Ledger Entry", dle_name, "amount")
	outstanding = max(0, amount - total_paid)
	status = "Paid" if outstanding <= 0 else "Partially Paid"

	frappe.db.set_value(
		"Debt Ledger Entry",
		dle_name,
		{"paid_amount": total_paid, "outstanding_amount": outstanding, "status": status},
		update_modified=False,
	)
