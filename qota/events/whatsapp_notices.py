# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""Payment and suspension notices on the official WhatsApp app.

The junta templates are already approved in Meta. Their variables are composed
here (receipt lines, suspension phase, amount) and are not fields of one
document, so the send goes through a WA Message with the parameters already
filled. The WA Template row stays unbound: a bound template would replace
those parameters on submit. A failed send stays on WA Message and does not
undo the receipt or the suspension.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, formatdate, fmt_money

LANGUAGE = "es"
FOOTER = "Junta Administradora de Agua · Notificaciones"
PAYMENT_TEMPLATE = "qota_payment_received"
SUSPENSION_TEMPLATE = "qota_service_suspension"

PAYMENT_HEADER = "Confirmación de Pago Recibido"
PAYMENT_BODY = """Hola *{{name}}*.

La Junta Administradora de Agua te confirma que se ha registrado el pago identificado con el recibo {{receipt}}, correspondiente al contrato {{contract}}, con fecha {{date}}.

*Detalle del pago:*
{{detail}}

Total recibido: {{amount}}

Para consultas o aclaraciones sobre este pago, comunícate con nuestra administración."""

SUSPENSION_HEADER = "Aviso de Suspensión del Servicio"
SUSPENSION_BODY = """Hola *{{name}}*.

La Junta Administradora de Agua te notifica que se ha emitido el aviso de suspensión {{suspension}}, correspondiente al contrato {{contract}}.

*Detalle de la notificación:*
{{message}}

Para consultas o aclaraciones sobre este aviso, comunícate con nuestra administración."""

SENT_STATUSES = ("Sent", "Delivered", "Read")


def enqueue_payment_notice(doc, method=None):
	_enqueue("notify_on_payment", "qota.events.whatsapp_notices.send_payment_notice", receipt_name=doc.name)


def enqueue_suspension_notice(doc, method=None):
	_enqueue(
		"notify_on_suspension",
		"qota.events.whatsapp_notices.send_suspension_notice",
		suspension_name=doc.name,
		phase="Scheduled",
	)


def enqueue_executed_suspension_notice(suspension_name):
	"""Notify after the plumbers record the technical cut."""
	_enqueue(
		"notify_on_suspension",
		"qota.events.whatsapp_notices.send_suspension_notice",
		suspension_name=suspension_name,
		phase="Executed",
	)


def send_payment_notice(receipt_name):
	"""Tell the subscriber that a payment receipt was submitted."""
	try:
		_send_payment_notice(receipt_name)
	except Exception:
		frappe.log_error(title="WhatsApp payment notice failed", message=frappe.get_traceback())


def send_suspension_notice(suspension_name, phase="Scheduled"):
	"""Tell the subscriber that a suspension was scheduled or that the cut was applied."""
	try:
		_send_suspension_notice(suspension_name, phase)
	except Exception:
		frappe.log_error(title="WhatsApp suspension notice failed", message=frappe.get_traceback())


@frappe.whitelist()
def send_test_message(phone):
	"""Send the payment template to one number so the connection can be checked."""
	frappe.only_for("System Manager")
	_use_template_language()
	if not _app_ready() or not _account():
		return _("The WhatsApp account is not active.")

	normalized = normalize_phone(phone)
	if not normalized:
		return _("The test phone is not a valid number.")

	sample_detail = "Cuota Mensual (01-2026): " + fmt_money(0)
	preview = _("Hello {0}. We received your payment of {1} for contract {2} on {3}. Detail: {4}.").format(
		"Prueba",
		fmt_money(0),
		"TEST",
		"01-01-2026",
		sample_detail,
	)
	sent = _deliver(
		phone=normalized,
		subscriber=None,
		reference_doctype=None,
		reference_name=None,
		template_name=(_notices().payment_template if _notices() else None) or PAYMENT_TEMPLATE,
		parameters=[
			("receipt", "TEST"),
			("name", "Prueba"),
			("contract", "TEST"),
			("date", "01-01-2026"),
			("detail", sample_detail),
			("amount", fmt_money(0)),
		],
		preview=preview,
		header=PAYMENT_HEADER,
		body=PAYMENT_BODY,
		label="Payment received",
	)
	if sent:
		return _("Test message sent to {0}.").format(normalized)
	return _("The test message was not sent. Open WA Message to see the reason.")


def normalize_phone(raw):
	"""Return a WhatsApp recipient. Honduras numbers of 8 digits gain the 504 prefix."""
	digits = "".join(character for character in str(raw or "") if character.isdigit())
	if digits.startswith("00"):
		digits = digits[2:]
	if len(digits) == 8:
		return "504" + digits
	if digits.startswith("504") and len(digits) == 11:
		return digits
	if 10 <= len(digits) <= 15:
		return digits
	return None


def ensure_notice_template(account, template_name, label, header, body, examples=None):
	"""Mirror an approved Meta template locally without pushing it again.

	Variable rows need an example because that child field is mandatory. The
	examples are not sent to Meta: the row is inserted as an already-synced
	template, so the official save does not call the Graph API.
	"""
	existing = frappe.db.get_value(
		"WA Template",
		{"template_name": template_name, "language": LANGUAGE, "whatsapp_account": account},
		"name",
	)
	if existing:
		return existing

	from whatsapp.whatsapp.doctype.wa_template.wa_template import get_template_variables

	examples = examples or {}
	names = list(dict.fromkeys([*get_template_variables(header), *get_template_variables(body)]))
	doc = frappe.new_doc("WA Template")
	doc.flags.from_sync = True
	doc.update(
		{
			"template_label": label,
			"template_name": template_name,
			"whatsapp_account": account,
			"status": "Approved",
			"template_type": "Utility",
			"language": LANGUAGE,
			"header_type": "Text",
			"header_text": header,
			"message": body,
			"footer": FOOTER,
			"variable_format": "Named",
			"template_variables": [
				{
					"variable_name": name,
					"variable_example": examples.get(name) or "ejemplo",
					"variable_field": "",
				}
				for name in names
			],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _send_payment_notice(receipt_name):
	_use_template_language()
	if _already_sent("Payment Receipt", receipt_name):
		return

	receipt = frappe.get_doc("Payment Receipt", receipt_name)
	amount = flt(receipt.total_to_pay)
	paid_on = formatdate(receipt.payment_date) if receipt.payment_date else "-"
	detail = _payment_detail(receipt)
	preview = _("Hello {0}. We received your payment of {1} for contract {2} on {3}. Detail: {4}.").format(
		receipt.full_name or "",
		fmt_money(amount),
		receipt.service_contract or "",
		paid_on,
		detail,
	)
	_send_for_subscriber(
		subscriber=receipt.subscriber,
		reference_doctype="Payment Receipt",
		reference_name=receipt.name,
		template_field="payment_template",
		fallback_template=PAYMENT_TEMPLATE,
		parameters=[
			("receipt", receipt.name),
			("name", receipt.full_name or "-"),
			("contract", receipt.service_contract or "-"),
			("date", paid_on),
			("detail", detail),
			("amount", fmt_money(amount)),
		],
		preview=preview,
		header=PAYMENT_HEADER,
		body=PAYMENT_BODY,
		label="Payment received",
		skip_reason=_("The receipt has no amount to confirm.") if amount <= 0 else None,
	)


def _send_suspension_notice(suspension_name, phase):
	_use_template_language()
	if phase not in ("Scheduled", "Executed"):
		phase = "Scheduled"
	if _already_sent("Service Suspension", suspension_name, phase):
		return

	suspension = frappe.get_doc("Service Suspension", suspension_name)
	reason = _(suspension.suspension_type) if suspension.suspension_type else "-"
	effective = formatdate(suspension.effective_date) if suspension.effective_date else "-"
	executed = formatdate(suspension.executed_date) if suspension.executed_date else effective
	if phase == "Executed":
		notice = _("the suspension cut was applied")
		notice_date = executed
		detail = _suspension_detail(suspension, reason)
		if suspension.executed_date and suspension.effective_date and str(suspension.executed_date) != str(
			suspension.effective_date
		):
			detail = _("{0} ‖ Scheduled for {1}").format(detail, effective)
	else:
		notice = _("the suspension was scheduled")
		notice_date = effective
		detail = _suspension_detail(suspension, reason)
	message = _("{0} with date {1}. Reason: {2}.").format(notice, notice_date, detail)
	preview = _("[{0}] Hello {1}. Suspension {2} for contract {3}: {4}.").format(
		phase,
		suspension.full_name or "",
		suspension.name,
		suspension.service_contract or "",
		message,
	)
	_send_for_subscriber(
		subscriber=suspension.subscriber,
		reference_doctype="Service Suspension",
		reference_name=suspension.name,
		template_field="suspension_template",
		fallback_template=SUSPENSION_TEMPLATE,
		parameters=[
			("name", suspension.full_name or "-"),
			("suspension", suspension.name),
			("contract", suspension.service_contract or "-"),
			("message", message),
		],
		preview=preview,
		header=SUSPENSION_HEADER,
		body=SUSPENSION_BODY,
		label="Service suspension",
	)


def _enqueue(flag, method, **kwargs):
	try:
		notices = _notices()
		if not _app_ready() or not _account() or not notices or not notices.get(flag):
			return
		frappe.enqueue(method, queue="short", enqueue_after_commit=True, **kwargs)
	except Exception:
		frappe.log_error(title="WhatsApp enqueue failed", message=frappe.get_traceback())


def _send_for_subscriber(
	subscriber,
	reference_doctype,
	reference_name,
	template_field,
	fallback_template,
	parameters,
	preview,
	header,
	body,
	label,
	skip_reason=None,
):
	notices = _notices()
	template_name = (notices.get(template_field) if notices else None) or fallback_template
	phone = frappe.db.get_value("Subscriber", subscriber, "primary_phone") if subscriber else None
	normalized = normalize_phone(phone)
	if skip_reason or not normalized:
		_record_skip(
			reference_doctype,
			reference_name,
			skip_reason or _("The subscriber has no valid phone."),
		)
		return

	_deliver(
		phone=normalized,
		subscriber=subscriber,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		template_name=template_name,
		parameters=parameters,
		preview=preview,
		header=header,
		body=body,
		label=label,
	)


def _deliver(
	phone,
	subscriber,
	reference_doctype,
	reference_name,
	template_name,
	parameters,
	preview,
	header,
	body,
	label,
):
	account = _account()
	if not account or not template_name:
		_record_skip(reference_doctype, reference_name, _("The WhatsApp account is not active."))
		return False

	template = ensure_notice_template(
		account,
		template_name,
		label,
		header,
		body,
		examples=_parameter_map(parameters),
	)
	if frappe.db.get_value("WA Template", template, "reference_doctype"):
		_record_skip(
			reference_doctype,
			reference_name,
			_("The WhatsApp template is bound to a DocType, so the notice was not sent."),
		)
		return False

	from qota.apis.whatsapp_inbox import link_subscriber, subscriber_for_phone
	from whatsapp.whatsapp.doctype.wa_profile.wa_profile import get_or_create_profile

	profile = get_or_create_profile(
		phone_number=f"+{phone}",
		account_name=account,
		profile_name=subscriber or phone,
		wa_id=phone,
	)
	link_subscriber(profile, subscriber or subscriber_for_phone(phone))

	doc = frappe.new_doc("WA Message")
	doc.flags.ignore_permissions = True
	doc.update(
		{
			"to": profile,
			"whatsapp_account": account,
			"direction": "Outgoing",
			"is_template": 1,
			"whatsapp_template": template,
			"message": preview,
			"reference_doctype": reference_doctype,
			"reference_docname": reference_name,
			"template_body_parameters": json.dumps(_parameter_map(parameters), ensure_ascii=False),
			"status": "Pending",
		}
	)
	try:
		doc.insert(ignore_permissions=True)
		doc.submit()
	except Exception:
		frappe.log_error(title="WhatsApp notice send failed", message=frappe.get_traceback())
		if doc.name and frappe.db.exists("WA Message", doc.name):
			if frappe.db.get_value("WA Message", doc.name, "status") != "Failed":
				frappe.db.set_value(
					"WA Message",
					doc.name,
					{"status": "Failed", "error_message": _("The notice was not sent.")},
					update_modified=False,
				)
		return False
	return frappe.db.get_value("WA Message", doc.name, "status") in SENT_STATUSES


def _parameter_map(parameters):
	return {name: _parameter(value) for name, value in parameters}


def _suspension_detail(suspension, reason):
	"""Reason, with the fine number when the cut is for an unpaid fine."""
	if suspension.service_fine:
		return f"{reason} ({suspension.service_fine})"
	return reason or "-"


def _payment_detail(receipt):
	"""Paid lines as 'Cuota Mensual (01-2026): L 125.00 ‖ ...'. Parameters cannot contain line breaks."""
	lines = []
	for item in receipt.payment_items or []:
		concept = _(item.payment_concept) if item.payment_concept else "-"
		period = (item.billing_period or "").strip()
		label = f"{concept} ({period})" if period else concept
		lines.append(f"{label}: {fmt_money(item.amount)}")
	return " ‖ ".join(lines) or "-"


def _parameter(value):
	text = " ".join(str(value or "-").split())
	return text[:1024] or "-"


def _already_sent(reference_doctype, reference_name, phase=None):
	filters = {
		"reference_doctype": reference_doctype,
		"reference_docname": reference_name,
		"status": ["in", list(SENT_STATUSES)],
	}
	if phase:
		filters["message"] = ["like", f"[{phase}]%"]
	return bool(frappe.db.exists("WA Message", filters))


def _use_template_language():
	frappe.local.lang = LANGUAGE


def _app_ready():
	return bool(frappe.db.exists("DocType", "WA Message") and frappe.db.exists("DocType", "WA Template"))


def _account():
	if not frappe.db.exists("DocType", "WA Settings"):
		return None
	name = frappe.db.get_single_value("WA Settings", "default_account")
	if not name or frappe.db.get_value("WA Account", name, "status") != "Active":
		return None
	return name


def _notices():
	if not frappe.db.exists("DocType", "WhatsApp Notifications"):
		return None
	return frappe.get_single("WhatsApp Notifications")


def _record_skip(reference_doctype, reference_name, message):
	if not frappe.db.exists("DocType", "WA Log"):
		frappe.logger("whatsapp").info(message)
		return
	from whatsapp.whatsapp.api.utils import log

	log(
		"Warning",
		"Message",
		message,
		account=_account(),
		reference_doctype=reference_doctype,
		reference_docname=reference_name,
	)
