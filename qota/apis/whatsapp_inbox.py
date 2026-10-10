# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""Phone threads on top of WA Profile and WA Message.

The official app stores each person as a profile and each text as a message.
It does not ship a desk inbox. A sender does not have to be a subscriber.
When the last 8 digits match Subscriber.primary_phone, the ficha is linked.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from qota.events.whatsapp_notices import normalize_phone


def list_conversations():
	_require_manager()
	if not frappe.db.exists("DocType", "WA Profile"):
		return []

	profiles = frappe.get_all(
		"WA Profile",
		filters={"status": ["!=", "Archived"]},
		fields=["name", "profile_name", "phone_number", "qota_last_seen"],
		limit=200,
	)
	if not profiles:
		return []

	names = [row.name for row in profiles]
	latest = {
		row.profile: row
		for row in frappe.db.sql(
			"""
			select m.`to` as profile, m.message, m.direction, m.status, m.creation
			from `tabWA Message` m
			inner join (
				select `to` as profile, max(creation) as creation
				from `tabWA Message`
				where `to` in %(names)s
				group by `to`
			) last on last.profile = m.`to` and last.creation = m.creation
			""",
			{"names": names},
			as_dict=True,
		)
	}
	unread = {
		row.profile: cint(row.unread)
		for row in frappe.db.sql(
			"""
			select m.`to` as profile, count(*) as unread
			from `tabWA Message` m
			inner join `tabWA Profile` p on p.name = m.`to`
			where m.direction = 'Incoming'
				and m.`to` in %(names)s
				and (p.qota_last_seen is null or m.creation > p.qota_last_seen)
			group by m.`to`
			""",
			{"names": names},
			as_dict=True,
		)
	}
	phones = _subscriber_phones()
	rows = []
	for profile in profiles:
		last = latest.get(profile.name)
		subscriber = _match_phone(profile.phone_number, phones)
		rows.append(
			{
				"name": profile.name,
				"phone": profile.phone_number,
				"contact_name": profile.profile_name or profile.phone_number,
				"subscriber": subscriber,
				"last_body": (last.message if last else "") or "",
				"last_direction": last.direction if last else "",
				"last_status": last.status if last else "",
				"last_on": last.creation if last else None,
				"unread": unread.get(profile.name, 0),
			}
		)
	rows.sort(key=lambda row: row["last_on"] or "", reverse=True)
	return rows


def thread(profile):
	_require_manager()
	if not frappe.db.exists("WA Profile", profile):
		frappe.throw(_("The conversation does not exist."))

	doc = frappe.get_doc("WA Profile", profile)
	subscriber = subscriber_for_phone(doc.phone_number)
	link_subscriber(doc.name, subscriber)
	if frappe.get_meta("WA Profile").has_field("qota_last_seen"):
		frappe.db.set_value("WA Profile", doc.name, "qota_last_seen", now_datetime(), update_modified=False)

	messages = frappe.get_all(
		"WA Message",
		filters={"to": doc.name},
		fields=["message", "direction", "status", "creation", "is_template"],
		order_by="creation asc",
		limit=300,
	)
	return {
		"conversation": {
			"name": doc.name,
			"phone": doc.phone_number,
			"contact_name": doc.profile_name or doc.phone_number,
			"subscriber": subscriber,
		},
		"messages": [
			{
				"body": message.message or "",
				"direction": message.direction,
				"status": message.status,
				"sent_on": message.creation,
			}
			for message in messages
		],
	}


def send_reply(profile, body):
	_require_manager()
	text = " ".join(str(body or "").split())
	if not text:
		frappe.throw(_("Write a message first."))
	if not frappe.db.exists("WA Profile", profile):
		frappe.throw(_("The conversation does not exist."))

	from whatsapp.whatsapp.api.messages import send_message

	send_message(to=profile, message=text)
	return True


def subscriber_for_phone(phone):
	return _match_phone(phone, _subscriber_phones())


def link_subscriber(profile_name, subscriber):
	"""Attach the ficha to the profile once. The official profile keeps its own links."""
	if not subscriber or not profile_name:
		return
	profile = frappe.get_doc("WA Profile", profile_name)
	if any(link.link_doctype == "Subscriber" and link.link_name == subscriber for link in profile.links or []):
		return
	profile.append("links", {"link_doctype": "Subscriber", "link_name": subscriber, "link_title": subscriber})
	profile.flags.ignore_permissions = True
	profile.save(ignore_permissions=True)


def _require_manager():
	frappe.only_for("System Manager")


def _subscriber_phones():
	cached = getattr(frappe.local, "qota_subscriber_phones", None)
	if cached is not None:
		return cached
	rows = frappe.get_all(
		"Subscriber",
		filters={"primary_phone": ["is", "set"]},
		fields=["name", "primary_phone"],
		limit=5000,
	)
	frappe.local.qota_subscriber_phones = rows
	return rows


def _match_phone(phone, rows):
	digits = _digits(normalize_phone(phone) or phone)
	if len(digits) < 8:
		return None
	tail = digits[-8:]
	for row in rows:
		if _digits(row.primary_phone)[-8:] == tail:
			return row.name
	return None


def _digits(value):
	return "".join(character for character in str(value or "") if character.isdigit())
