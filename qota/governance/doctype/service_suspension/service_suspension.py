# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, fmt_money, formatdate, getdate, today

from qota.governance.doctype.service_contract.service_contract import update_contract_property


class ServiceSuspension(Document):
	"""
	Manages service suspension.
	Updates contract status and records final readings only
	for metered services.
	"""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amended_from: DF.Link | None
		billing_basis: DF.Literal["", "Flat Rate", "Metered"]
		edit_posting_date: DF.Check
		effective_date: DF.Date | None
		executed_date: DF.Date | None
		final_reading: DF.Float
		full_name: DF.Data | None
		posting_date: DF.Datetime
		premises: DF.Link | None
		remarks: DF.SmallText | None
		service_contract: DF.Link
		service_fine: DF.Link | None
		status: DF.Literal["Draft", "Scheduled", "Executed"]
		subscriber: DF.Link | None
		suspension_type: DF.Literal["Subscriber Request", "Arrears", "By Fine"]
	# end: auto-generated types

	def validate(self) -> None:
		self.validate_contract_eligibility()
		self.validate_posting_date()
		self.validate_suspension_rules()
		self.set_default_remarks()

		if self.status == "Executed":
			self.validate_technical_execution()

	def set_default_remarks(self) -> None:
		"""Populate remarks with a default message if not already set."""
		if self.remarks:
			return
		if not self.suspension_type:
			return

		if self.suspension_type == "Arrears":
			from qota.billing.doctype.debt_refinancing.debt_refinancing import get_contract_balance

			outstanding = get_contract_balance(self.service_contract)
			self.remarks = (
				f"{_('Suspension Reason')}: {_(self.suspension_type)} | "
				f"{_('Outstanding Debt')}: {frappe.utils.fmt_money(outstanding)}"
			)
		else:
			self.remarks = f"{_('Suspension Reason')}: {_(self.suspension_type)}"

	def validate_contract_eligibility(self) -> None:
		"""Checks if the contract is Active and ready for suspension."""
		status = frappe.db.get_value("Service Contract", self.service_contract, "status", for_update=True)
		if status == "Suspended" and self.is_new():
			frappe.throw(_("Contract {0} is already suspended.").format(self.service_contract))

		if status in ["Closed", "Cancelled"]:
			frappe.throw(_("Cannot suspend a contract in '{0}' status.").format(status))

		duplicate_order = frappe.db.exists(
			"Service Suspension",
			{
				"service_contract": self.service_contract,
				"status": ["in", ["Draft", "Scheduled"]],
				"name": ["!=", self.name],
				"docstatus": ["<", 2],
			},
		)

		if duplicate_order:
			frappe.throw(
				_("There is already a pending suspension order ({0}) for this contract.").format(
					duplicate_order
				)
			)

	def validate_posting_date(self) -> None:
		"""Ensures the suspension date is not before the contract start."""
		start_date = frappe.db.get_value("Service Contract", self.service_contract, "start_date")
		if getdate(self.posting_date) < getdate(start_date):
			frappe.throw(_("Suspension date cannot be earlier than contract start date."))

	def validate_suspension_rules(self) -> None:
		"""
		One field classifies the cut.
		1. Subscriber Request: no Monthly Bills on or after the effective date,
		   and no earlier unpaid debts.
		2. By Fine: link the unpaid Service Fine of this contract.
		   Monthly fees may be current.
		3. Arrears: expired Monthly Fee threshold.
		"""
		if self.suspension_type != "By Fine":
			self.service_fine = None

		if self.suspension_type == "By Fine":
			self.validate_service_fine()
			return

		settings = frappe.get_doc("Billing Settings")
		eff_date = getdate(self.effective_date)

		if self.suspension_type == "Subscriber Request":
			existing_bill = frappe.db.exists(
				"Monthly Bill",
				{
					"service_contract": self.service_contract,
					"start_date": [">=", eff_date],
					"docstatus": ["!=", 2],
				},
			)

			if existing_bill:
				frappe.throw(
					_(
						"Cannot suspend retroactively to {0}. "
						"Monthly Bill {1} already exists "
						"within or after this period. "
						"Cancel the bills first or adjust the Effective Date."
					).format(frappe.utils.formatdate(eff_date), existing_bill)
				)

			previous_debts = frappe.get_all(
				"Debt Ledger Entry",
				filters={
					"service_contract": self.service_contract,
					"status": ["in", ["Unpaid", "Partially Paid"]],
					"due_date": ["<", eff_date],
					"docstatus": ["!=", 2],
				},
			)
			if previous_debts:
				frappe.throw(_("Subscriber has unpaid debts prior to the requested suspension date."))

		elif self.suspension_type == "Arrears":
			all_unpaid_debts = frappe.get_all(
				"Debt Ledger Entry",
				filters={
					"service_contract": self.service_contract,
					"entry_type": "Monthly Fee",
					"status": ["in", ["Unpaid", "Partially Paid"]],
					"docstatus": ["!=", 2],
				},
				fields=["due_date", "outstanding_amount"],
			)

			grace_days = flt(settings.grace_period or 0)

			expired_debts = [
				d for d in all_unpaid_debts if eff_date > getdate(add_days(d.due_date, grace_days))
			]

			total_expired_sum = sum(flt(d.outstanding_amount) for d in expired_debts)

			if total_expired_sum <= 0.01:
				frappe.throw(
					_("Suspension for outstanding debt requires expired monthly fees as of the Effective Date.")
				)

			limit_months = int(settings.suspension_months_limit or 2)
			if len(expired_debts) < limit_months:
				frappe.throw(
					_("Threshold not met at {0}. Required: {1} months. Current expired: {2}.").format(
						formatdate(eff_date), limit_months, len(expired_debts)
					)
				)

			min_debt = flt(settings.min_debt_for_suspension or 0)
			if total_expired_sum < min_debt:
				frappe.throw(
					_("Total expired debt ({0}) is below the minimum threshold ({1}).").format(
						fmt_money(total_expired_sum), fmt_money(min_debt)
					)
				)
		else:
			frappe.throw(_("Select a suspension reason."))

	def validate_service_fine(self) -> None:
		"""A sanction cut needs the unpaid fine of this same contract."""
		if not self.service_fine:
			frappe.throw(
				_(
					"Link the unpaid Service Fine. Monthly payments can be current. "
					"The suspension order is what cuts the service."
				)
			)

		fine = frappe.db.get_value(
			"Service Fine",
			self.service_fine,
			["service_contract", "docstatus", "status"],
			as_dict=True,
		)
		if not fine or fine.service_contract != self.service_contract or fine.docstatus != 1 or fine.status != "Unpaid":
			frappe.throw(_("The Service Fine must be submitted, unpaid, and for this contract."))

		already = frappe.db.exists(
			"Service Suspension",
			{
				"service_fine": self.service_fine,
				"docstatus": ["<", 2],
				"name": ["!=", self.name],
			},
		)
		if already:
			frappe.throw(
				_("Service Fine {0} is already linked to suspension {1}.").format(self.service_fine, already)
			)

	def validate_technical_execution(self) -> None:
		"""Validates final readings if the service is metered."""
		if self.billing_basis == "Metered":
			if not self.final_reading:
				frappe.throw(_("Final Reading is mandatory for metered services."))

			last_reading = frappe.db.get_value(
				"Meter Reading",
				{"service_contract": self.service_contract, "docstatus": 1},
				"current_reading",
				order_by="reading_date desc, creation desc",
			)

			if last_reading and flt(self.final_reading) < flt(last_reading):
				frappe.throw(
					_("Final reading ({0}) cannot be lower than the last recorded reading ({1}).").format(
						self.final_reading, last_reading
					)
				)

	def on_submit(self) -> None:
		if self.status == "Draft":
			self.db_set("status", "Scheduled")

	def before_cancel(self) -> None:
		if self.status == "Executed" or self.executed_date:
			frappe.throw(_("An executed suspension cannot be cancelled."))
		self._throw_if_fine_has_payments()

	def _throw_if_fine_has_payments(self) -> None:
		"""A paid fine stays until its receipts are cancelled."""
		if not self.service_fine:
			return

		paid_amount = frappe.db.get_value(
			"Debt Ledger Entry",
			{
				"reference_doctype": "Service Fine",
				"reference_name": self.service_fine,
				"docstatus": 1,
			},
			"paid_amount",
		)
		if flt(paid_amount) <= 0:
			return

		frappe.throw(
			_(
				"Cannot cancel this suspension because Service Fine {0} has recorded payments ({1}). "
				"Cancel the related Payment Receipts first."
			).format(
				self.service_fine,
				frappe.format_value(paid_amount, {"fieldtype": "Currency"}),
			)
		)

	def on_cancel(self) -> None:
		update_contract_property(
			service_contract=self.service_contract,
			update_type="Status",
			data={
				"new_status": "Active",
				"suspension_reason": None,
				"date": today(),
				"description": _("Suspension order {0} cancelled. Restoring activity markers.").format(
					self.name
				),
			},
		)

		frappe.db.set_value(
			"Service Contract", self.service_contract, {"suspended_since": None, "suspension_reason": ""}
		)

		# Scheduled orders have not produced a technical reading. Existing
		# readings of the contract belong to independent billing operations.
		self.db_set("status", "Draft")

	def cancel_linked_meter_readings(self) -> None:
		"""
		Finds and cancels any submitted Meter Reading created
		by this suspension order.
		"""
		linked_readings = frappe.get_all(
			"Meter Reading",
			filters={
				"service_contract": self.service_contract,
				"docstatus": 1,
			},
			pluck="name",
		)

		for reading_name in linked_readings:
			try:
				reading_doc = frappe.get_doc("Meter Reading", reading_name)
				reading_doc.cancel()
				frappe.msgprint(_("Meter Reading {0} has been cancelled.").format(reading_name), alert=True)
			except Exception:
				frappe.log_error(
					message=frappe.get_traceback(),
					title=_("Error cancelling meter reading {0} during suspension rollback").format(
						reading_name
					),
				)

	@frappe.whitelist()
	def execute_suspension_logic(self, final_reading: float, executed_date: str) -> None:
		"""
		Finalizes the technical process.

		Updates the Service Contract status to 'Suspended' and mirrors
		the specific reason for better administrative visibility.
		"""
		self.check_permission("write")
		self.reload()
		contract = frappe.db.get_value("Service Contract", self.service_contract, ["docstatus", "status"], as_dict=True, for_update=True)
		current = frappe.db.get_value(self.doctype, self.name, ["docstatus", "status", "executed_date"], as_dict=True, for_update=True)
		if not current or current.docstatus != 1 or current.status != "Scheduled" or current.executed_date:
			frappe.throw(_("Only a submitted scheduled suspension can be executed."))
		if not contract or contract.docstatus != 1 or contract.status != "Active":
			frappe.throw(_("A formalized active contract is required for suspension execution."))
		if not executed_date:
			frappe.throw(_("An execution date is required."))
		getdate(executed_date)
		self.reload()
		self.final_reading = flt(final_reading)
		self.executed_date = executed_date
		self.status = "Executed"
		self.validate_technical_execution()

		update_contract_property(
			service_contract=self.service_contract,
			update_type="Status",
			data={
				"new_status": "Suspended",
				"suspension_reason": self.suspension_type,
				"date": self.executed_date,
				"description": _("Service suspended technically on {0}. Effective since {1}.").format(
					formatdate(self.executed_date), formatdate(self.effective_date)
				),
			},
		)

		frappe.db.set_value(
			"Service Contract",
			self.service_contract,
			{"suspended_since": self.effective_date, "reactivation_date": None},
		)

		if self.billing_basis == "Metered":
			self.create_technical_reading()

		self.save()
		self.run_method("on_technical_execution")

	def create_technical_reading(self) -> None:
		"""Generates a Meter Reading document to stop the billing cycle."""
		reading = frappe.new_doc("Meter Reading")
		reading.service_contract = self.service_contract
		reading.reading_date = self.executed_date
		reading.current_reading = self.final_reading
		reading.remarks = _("Closure reading (Suspension {0})").format(self.name)
		reading.insert(ignore_permissions=True)
		reading.submit()
