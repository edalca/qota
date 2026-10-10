# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe

from qota.apis.whatsapp_inbox import list_conversations as _list
from qota.apis.whatsapp_inbox import send_reply as _send
from qota.apis.whatsapp_inbox import thread as _thread


@frappe.whitelist()
def list_conversations():
	return _list()


@frappe.whitelist()
def thread(conversation):
	return _thread(conversation)


@frappe.whitelist()
def send_reply(conversation, body):
	return _send(conversation, body)
