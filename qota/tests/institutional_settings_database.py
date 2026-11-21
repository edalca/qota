# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""Opt-in installed institutional configuration tests on qota.localhost only.

Every settings mutation and synthetic user is rolled back. No fixtures are
committed.
"""

from contextlib import ExitStack
import os
import unittest
import uuid
from datetime import date, time
from unittest.mock import patch

import frappe

from qota.governance import institutional as office
from qota.tests.institutional_settings import configuration, exception, location

CHILDREN = {
	"weekly_hours": "Institutional Weekly Hours",
	"calendar_exceptions": "Institutional Calendar Exception",
	"exception_hours": "Institutional Exception Hours",
	"office_locations": "Institutional Office Location",
}


def connect_local():
	site = os.environ.get("QOTA_TEST_SITE", "qota.localhost")
	sites_path = "/home/frappe/frappe-bench/sites"
	frappe.init(site=site, sites_path=sites_path)
	os.chdir(sites_path)
	frappe.connect()
	frappe.set_user("Administrator")


class InstitutionalDatabaseTests(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self.stack = ExitStack()
		self.stack.enter_context(patch.object(frappe.db, "commit", lambda: None))
		self.addCleanup(self.finish)
		self.initial = frappe.get_doc(office.SETTINGS).as_dict()

	def finish(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_document_cache(office.SETTINGS, office.SETTINGS)
		self.assertEqual(frappe.get_doc(office.SETTINGS).as_dict(), self.initial)
		self.stack.close()

	def save(self, data=None):
		doc = frappe.get_doc(office.SETTINGS)
		for key in CHILDREN:
			doc.set(key, (data or configuration()).get(key, []))
		return doc.save()

	def user(self, manager=False):
		name = "qota-p02-test-" + uuid.uuid4().hex + "@example.invalid"
		frappe.get_doc(dict(doctype="User", name=name, email=name, first_name="Institutional Test",
			enabled=1, user_type="System User")).db_insert()
		if manager:
			frappe.get_doc(dict(doctype="Has Role", parent=name, parenttype="User", parentfield="roles", role="System Manager")).db_insert()
		return name

	def test_installed_single_child_tables_and_administrative_permissions(self):
		meta = frappe.get_meta(office.SETTINGS)
		self.assertTrue(meta.issingle)
		self.assertTrue(meta.track_changes)
		self.assertEqual(meta.module, "Governance")
		source = frappe.get_file_json(frappe.get_app_path(
			"qota", "governance", "doctype", "institutional_settings", "institutional_settings.json"))
		self.assertEqual([(row["role"], row["read"], row["write"], row["create"]) for row in source["permissions"]],
			[("System Manager", 1, 1, 1)])
		self.assertIn(("System Manager", 1, 1, 1), {(p.role, p.read, p.write, p.create) for p in meta.permissions})
		for field, doctype in CHILDREN.items():
			self.assertEqual(meta.get_field(field).options, doctype)
			self.assertTrue(frappe.get_meta(doctype).istable)
			self.assertFalse(frappe.get_meta(doctype).permissions)
			self.assertTrue(frappe.db.table_exists(doctype))
			engine = frappe.db.sql("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s", ("tab" + doctype,))
			self.assertEqual(engine, (("InnoDB",),))
		self.assertEqual(frappe.db.get_single_value("System Settings", "time_zone"), office.TIMEZONE)

	def test_save_intervals_exceptions_and_private_reason(self):
		data = configuration()
		exception(data, date(2026, 10, 12), internal_reason="PRIVATE-INSTITUTIONAL-TEST")
		self.save(data)
		doc = frappe.get_doc(office.SETTINGS)
		self.assertEqual(len(doc.weekly_hours), 7)
		for key, doctype in CHILDREN.items():
			for row in doc.get(key):
				self.assertEqual((row.parent, row.parenttype, row.parentfield), (office.SETTINGS, office.SETTINGS, key))
				self.assertEqual(row.doctype, doctype)
		self.assertEqual(doc.calendar_exceptions[0].internal_reason, "PRIVATE-INSTITUTIONAL-TEST")
		self.assertTrue(doc.calendar_exceptions[0].public_reason in (None, ""))

	def test_open_exception_single_interval_persists(self):
		data = configuration()
		exception(data, date(2026, 10, 17), kind="Exceptional Hours", status="Open")
		data["exception_hours"] = [dict(exception_date="2026-10-17", start_time="08:00", end_time="10:00")]
		self.save(data)
		saved = frappe.get_doc(office.SETTINGS)
		self.assertEqual(len(saved.exception_hours), 1)
		self.assertEqual(str(saved.exception_hours[0].exception_date), "2026-10-17")
		self.assertEqual(str(saved.calendar_exceptions[0].exception_date), "2026-10-17")
		self.assertEqual(office._time(saved.exception_hours[0].start_time), time(8, 0))
		self.assertEqual(office._time(saved.exception_hours[0].end_time), time(10, 0))
		data["exception_hours"][0]["start_time"] = "00:00"
		self.save(data)
		self.assertEqual(office._time(frappe.get_doc(office.SETTINGS).exception_hours[0].start_time), time(0, 0))
		frappe.get_doc(office.SETTINGS).save()

	def test_model_rejects_contradictions_and_preserves_saved_data(self):
		self.save()
		for change in ("overlap", "missing_day", "duplicate_exception", "invalid_time", "overnight", "orphan", "location_conflict"):
			with self.subTest(change=change):
				data = configuration()
				if change == "overlap":
					data["weekly_hours"].insert(1, dict(weekday="Monday", day_status="Open", start_time="09:00", end_time="11:00"))
				elif change == "missing_day":
					data["weekly_hours"].pop()
				elif change == "duplicate_exception":
					exception(data); exception(data)
				elif change in {"invalid_time", "overnight"}:
					data["weekly_hours"][0].update(start_time="24:00" if change == "invalid_time" else "22:00", end_time="02:00")
				elif change == "orphan":
					data["exception_hours"] = [dict(exception_date="2026-10-12", start_time="08:00", end_time="12:00")]
				else:
					data["office_locations"] = [location(date(2026, 10, 1)), location(date(2026, 10, 1), address="Other synthetic address")]
				with self.assertRaises(frappe.ValidationError):
					self.save(data)
		self.assertEqual(len(frappe.get_doc(office.SETTINGS).weekly_hours), 7)

	def test_manager_can_edit_ordinary_and_guest_cannot_read_or_write_configuration(self):
		manager, ordinary = self.user(True), self.user(False)
		frappe.set_user(manager)
		self.assertTrue(frappe.has_permission(office.SETTINGS, "read"))
		self.save()
		for user in (ordinary, "Guest"):
			frappe.set_user(user)
			for permission in ("read", "write", "create", "delete"):
				self.assertFalse(frappe.has_permission(office.SETTINGS, permission))
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(office.SETTINGS).check_permission("read")
			with self.assertRaises(frappe.PermissionError):
				self.save()
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(office.SETTINGS).save(ignore_permissions=True)
			for doctype in CHILDREN.values():
				self.assertFalse(frappe.has_permission(doctype, "write", parent_doctype=office.SETTINGS))

	def test_empty_configuration_is_saved_without_invented_defaults(self):
		self.save({key: [] for key in CHILDREN})
		doc = frappe.get_doc(office.SETTINGS)
		for key in CHILDREN:
			self.assertEqual(doc.get(key), [])

	def test_locations_and_scheduled_move_persist(self):
		data = configuration()
		data["office_locations"] = [location(date(2026, 10, 1), address="Synthetic current office", references="Synthetic reference"),
			location(date(2026, 10, 14), address="Synthetic future office", google_maps_url="https://www.google.com/maps", maps_verified=0)]
		self.save(data)
		saved = frappe.get_doc(office.SETTINGS).office_locations
		self.assertEqual([row.address for row in saved], ["Synthetic current office", "Synthetic future office"])
		self.assertEqual(str(saved[0].effective_from), "2026-10-01")
		self.assertEqual(str(saved[1].effective_from), "2026-10-14")
		self.assertEqual(saved[0].references, "Synthetic reference")
		self.assertEqual(saved[1].maps_verified, 0)
		self.assertEqual(saved[1].google_maps_url, "https://www.google.com/maps")
		data["office_locations"][1]["maps_verified"] = 1
		self.save(data)
		verified = frappe.get_doc(office.SETTINGS).office_locations[1]
		self.assertEqual(verified.maps_verified, 1)
		self.assertEqual(verified.google_maps_url, "https://www.google.com/maps")
		data["office_locations"][1]["publication_approved"] = 0
		self.save(data)
		unpublished = frappe.get_doc(office.SETTINGS).office_locations[1]
		self.assertEqual(unpublished.publication_approved, 0)
		self.assertEqual(unpublished.address, "Synthetic future office")

	def test_saved_exception_replaces_the_previous_calendar(self):
		self.save()
		self.assertEqual(frappe.get_doc(office.SETTINGS).calendar_exceptions, [])
		data = configuration()
		exception(data)
		self.save(data)
		self.assertEqual(len(frappe.get_doc(office.SETTINGS).calendar_exceptions), 1)
		self.save()
		self.assertEqual(frappe.get_doc(office.SETTINGS).calendar_exceptions, [])

	def test_edit_move_and_delete_exception_keep_unrelated_data(self):
		data = configuration()
		data["office_locations"] = [location(date(2026, 10, 1))]
		exception(data, kind="Exceptional Hours", status="Open", internal_reason="Initial private reason")
		data["exception_hours"] = [dict(exception_date="2026-10-12", start_time="08:00", end_time="10:00")]
		exception(data, date(2026, 10, 20))
		self.save(data)
		doc = frappe.get_doc(office.SETTINGS)
		def business_rows(rows):
			return [{k: v for k, v in r.as_dict().items() if k not in {"modified", "modified_by"}} for r in rows]
		weekly, locations = business_rows(doc.weekly_hours), business_rows(doc.office_locations)
		doc.calendar_exceptions[0].update(dict(exception_date="2026-10-17", internal_reason="Updated private reason"))
		doc.exception_hours[0].update(dict(exception_date="2026-10-17", start_time="10:00", end_time="11:00"))
		doc.save()
		loaded = frappe.get_doc(office.SETTINGS)
		self.assertEqual(str(loaded.exception_hours[0].exception_date), "2026-10-17")
		self.assertEqual(loaded.calendar_exceptions[0].internal_reason, "Updated private reason")
		self.assertEqual(office._time(loaded.exception_hours[0].start_time), time(10, 0))
		self.assertEqual(office._time(loaded.exception_hours[0].end_time), time(11, 0))
		loaded.remove(loaded.calendar_exceptions[0]); loaded.set("exception_hours", []); loaded.save()
		loaded = frappe.get_doc(office.SETTINGS)
		self.assertEqual(len(loaded.calendar_exceptions), 1)
		self.assertEqual(str(loaded.calendar_exceptions[0].exception_date), "2026-10-20")
		self.assertEqual(loaded.exception_hours, [])
		self.assertEqual(business_rows(loaded.weekly_hours), weekly)
		self.assertEqual(business_rows(loaded.office_locations), locations)

	def test_direct_saves_reject_private_policy_and_multiple_intervals(self):
		self.save()
		for invalid in ("missing_reason", "public_reason", "multiple", "old_type", "mismatched_date"):
			with self.subTest(invalid=invalid):
				data = configuration()
				exception(data, kind="Exceptional Hours", status="Open")
				data["exception_hours"] = [dict(exception_date="2026-10-12", start_time="08:00", end_time="10:00")]
				if invalid == "missing_reason": data["calendar_exceptions"][0]["internal_reason"] = " "
				elif invalid == "public_reason": data["calendar_exceptions"][0]["public_reason"] = "PRIVATE"
				elif invalid == "old_type": data["calendar_exceptions"][0]["exception_type"] = "Special Day"
				elif invalid == "mismatched_date": data["exception_hours"][0]["exception_date"] = "2026-10-13"
				else: data["exception_hours"].append(dict(exception_date="2026-10-12", start_time="11:00", end_time="12:00"))
				with self.assertRaises(frappe.ValidationError): self.save(data)
		self.assertEqual(frappe.get_doc(office.SETTINGS).calendar_exceptions, [])

	def test_direct_child_writes_cannot_bypass_whole_calendar_validation(self):
		data = configuration()
		exception(data, kind="Exceptional Hours", status="Open")
		data["exception_hours"] = [dict(exception_date="2026-10-12", start_time="08:00", end_time="10:00")]
		self.save(data)
		doc = frappe.get_doc(office.SETTINGS)
		for child in (doc.calendar_exceptions[0], doc.exception_hours[0]):
			with self.assertRaises(frappe.ValidationError): child.save()
			with self.assertRaises(frappe.ValidationError): child.delete()
		for doctype in ("Institutional Calendar Exception", "Institutional Exception Hours"):
			child = frappe.get_doc(dict(doctype=doctype, parent=office.SETTINGS, parenttype=office.SETTINGS,
				parentfield="calendar_exceptions" if doctype == "Institutional Calendar Exception" else "exception_hours"))
			with self.assertRaises(frappe.ValidationError): child.insert(ignore_permissions=True)

	def test_calendar_surface_schema_and_server_clock_permissions(self):
		from datetime import datetime, timezone
		from qota.governance.doctype.institutional_settings.institutional_settings import calendar_context
		meta = frappe.get_meta(office.SETTINGS)
		self.assertEqual([f.label for f in meta.fields if f.fieldtype == "Tab Break"], ["Office Hours", "Office Location"])
		self.assertEqual(meta.get_field("calendar_exceptions_html").fieldtype, "HTML")
		for field in ("calendar_exceptions", "exception_hours"):
			self.assertTrue(meta.get_field(field).hidden)
		self.assertFalse(meta.get_field("weekly_hours").hidden)
		with patch("frappe.utils.get_datetime_in_timezone", return_value=datetime(2026, 10, 13, 5, 59, tzinfo=timezone.utc)):
			self.assertEqual(calendar_context(), {"today": "2026-10-12", "timezone": office.TIMEZONE})
		for user in (self.user(False), "Guest"):
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError): calendar_context()


def run_local_tests():
	connect_local()
	try:
		result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InstitutionalDatabaseTests))
		frappe.db.rollback()
		return result.wasSuccessful()
	finally:
		frappe.db.rollback()
		frappe.destroy()


if __name__ == "__main__":
	raise SystemExit(0 if run_local_tests() else 1)
