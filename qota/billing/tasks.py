# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import calendar
from datetime import date as _date

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today


MONTH_NAMES = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]


def run_monthly_billing_cycle():
	"""
	Scheduled monthly job: automatically creates and submits a Flat Rate
	Billing Cycle for the previous calendar month.

	Only runs when auto_billing_enabled is set in Billing Settings.
	Processes all billing bases (Flat Rate and Metered).
	Skips silently if a cycle already exists for the target period.
	Errors are written to the Frappe Error Log for administrator review.
	"""
	settings = frappe.get_doc("Billing Settings")

	if not getattr(settings, "auto_billing_enabled", False):
		return

	curr = getdate(today())
	curr_month = curr.month
	curr_year = curr.year

	# Determine the previous month
	if curr_month == 1:
		prev_month = 12
		prev_year = curr_year - 1
	else:
		prev_month = curr_month - 1
		prev_year = curr_year

	fiscal_month = MONTH_NAMES[prev_month - 1]
	cycle_start_day = int(getattr(settings, "cycle_start_day", None) or 1)

	# Clamp to valid days in each month (handles months shorter than cycle_start_day)
	last_day_prev = calendar.monthrange(prev_year, prev_month)[1]
	safe_start_day = min(cycle_start_day, last_day_prev)
	start_date = _date(prev_year, prev_month, safe_start_day)

	last_day_curr = calendar.monthrange(curr_year, curr_month)[1]
	safe_curr_day = min(cycle_start_day, last_day_curr)
	end_date = add_days(_date(curr_year, curr_month, safe_curr_day), -1)

	# Locate an open Billing Year for the target period
	billing_year = frappe.db.get_value(
		"Billing Year",
		{"year_name": prev_year, "is_closed": 0},
		"name",
	)
	if not billing_year:
		frappe.log_error(
			title=_("Auto Billing: Billing Year Not Found"),
			message=_(
				"No open Billing Year found for {0}. "
				"Create an open Billing Year for this period "
				"or disable Auto Billing in Billing Settings."
			).format(prev_year),
		)
		return

	# Skip if a cycle already exists for this fiscal month (duplicate-safe)
	existing = frappe.db.exists(
		"Billing Cycle",
		{
			"fiscal_year": billing_year,
			"fiscal_month": fiscal_month,
			"docstatus": ["!=", 2],
		},
	)
	if existing:
		return

	try:
		cycle = frappe.new_doc("Billing Cycle")
		cycle.fiscal_year = billing_year
		cycle.fiscal_month = fiscal_month
		cycle.billing_basis = "All"
		cycle.start_date = str(start_date)
		cycle.end_date = str(end_date)
		cycle.posting_date = str(curr)
		cycle.edit_posting_date = 0
		cycle.insert(ignore_permissions=True)
		cycle.submit()
		frappe.db.commit()
	except Exception:
		frappe.log_error(
			title=_("Auto Billing: Cycle Creation Failed"),
			message=frappe.get_traceback(),
		)
