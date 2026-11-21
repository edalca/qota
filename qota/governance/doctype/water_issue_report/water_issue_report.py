"""Immutable report receipts with a single administrative read acknowledgment."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import validate_name
from frappe.utils import now_datetime


def require_manager():
    if not frappe.session.user or frappe.session.user == "Guest":
        raise frappe.PermissionError("Authentication required.")
    frappe.only_for("System Manager")


def report_text(value):
    return isinstance(value, str) and 5 <= len(value.strip()) <= 4000 and not any(
        ord(char) < 32 and char not in "\n\r\t" for char in value)


CONTENT_FIELDS = (
    "description",
    "location",
    "contracts_json",
    "conversation_session",
    "conversation_turn",
    "process_execution",
    "bot_flow",
)
REFERENCE_FIELDS = (
    "conversation_session",
    "conversation_turn",
    "process_execution",
    "bot_flow",
)


class WaterIssueReport(Document):
	def db_insert(self, *args, **kwargs):
		# A direct write is a new report, so an extension sees the same create path as insert.
		# Document flags and skipped lifecycle validation cannot grant this write.
		self.set("__islocal", True)
		self.validate()
		if type(self).validate is not WaterIssueReport.validate:
			WaterIssueReport.validate(self)
		return super().db_insert(*args, **kwargs)

	def db_update(self):
		self.validate()
		if type(self).validate is not WaterIssueReport.validate:
			WaterIssueReport.validate(self)
		return super().db_update()

	def autoname(self):
		self.name = self.process_execution

	def validate(self):
		if self.is_new() or not self.name:
			# ignore_permissions satisfies the role check. It does not skip integrity.
			self.check_permission("create")
			self._validate_new()
			self._validate_length()
		else:
			require_manager()
			previous = self.get_doc_before_save()
			if previous is None:
				try:
					previous = frappe.get_doc(self.doctype, self.name)
				except frappe.DoesNotExistError:
					frappe.throw(_("Water report content and references are immutable."))
			if any(self.get(key) != previous.get(key) for key in CONTENT_FIELDS) or self.name != previous.name:
				frappe.throw(_("Water report content and references are immutable."))
			if self.status not in ("Pending", "Seen") or (previous.status == "Seen" and self.status != "Seen"):
				frappe.throw(_("A water report can only be marked as Seen."))
			if previous.status == "Pending" and self.status == "Seen":
				self.seen_by, self.seen_at = frappe.session.user, now_datetime()
			else:
				self.seen_by, self.seen_at = previous.seen_by, previous.seen_at

	def _validate_new(self):
		if not self.status:
			self.status = "Pending"
		if self.status != "Pending" or self.seen_by or self.seen_at:
			frappe.throw(_("A water report must start as Pending without an acknowledgment."))
		if not report_text(self.description) or not report_text(self.location):
			frappe.throw(_("A textual description and a localizable location are required."))
		if not all(isinstance(self.get(fieldname), str) and self.get(fieldname) for fieldname in REFERENCE_FIELDS):
			frappe.throw(
				_("Conversation session, conversation turn, process execution, and bot flow are required.")
			)
		self._bind_name()

	def _bind_name(self):
		bound = validate_name(self.doctype, self.process_execution)
		if (self.name and self.name != bound) or bound != self.process_execution:
			frappe.throw(_("The water report name must match its process execution."))
		self.name = bound

	def before_rename(self, *args, **kwargs):
		frappe.throw(_("Water report content and references are immutable."))
