# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""Deterministic office calendar tests without site initialization or network."""

import copy
import unittest
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch

from qota.governance import institutional as office

DAY = date(2026, 10, 12)


def configuration():
	return {"weekly_hours": [
		{"weekday": day, "day_status": "Open" if index < 5 else "Closed",
			**({"start_time": "08:00", "end_time": "12:00"} if index < 5 else {})}
		for index, day in enumerate(office.WEEKDAYS)],
		"calendar_exceptions": [], "exception_hours": [], "office_locations": []}


def exception(doc, day=DAY, kind="Holiday", status="Closed", **extra):
	if kind != "Holiday":
		extra.setdefault("internal_reason", "Synthetic internal reason")
	doc["calendar_exceptions"].append(dict(exception_date=day, exception_type=kind, day_status=status, **extra))


def location(day=DAY, address="Synthetic test office", **extra):
	return dict({"effective_from": day, "address": address, "publication_approved": 1}, **extra)


class InstitutionalTests(unittest.TestCase):
	def setUp(self):
		self.doc = configuration()

	def read(self, at):
		return office.information_from_document(self.doc, at)

	def validate(self):
		office.validate_configuration(self.doc, today=DAY)

	def test_empty_is_unavailable_not_a_configured_closure(self):
		result = office.information_from_document({}, DAY)
		self.assertEqual(result["hours"]["status"], "Unavailable")
		self.assertIsNone(result["hours"]["closed"])
		self.assertEqual(result["location"]["status"], "Unavailable")

	def test_start_inclusive_end_exclusive_and_nonworking_day(self):
		self.validate()
		self.assertEqual(len(self.read(DAY)["hours"]["ordinary_week"]), 7)
		self.assertIsNone(self.read("2026-10-12")["hours"]["within_hours"])
		for clock, expected in (("07:59:59", False), ("08:00:00", True), ("11:59:59", True), ("12:00:00", False)):
			self.assertEqual(self.read(f"2026-10-12T{clock}")["hours"]["within_hours"], expected)
		self.assertTrue(self.read(date(2026, 10, 17))["hours"]["closed"])

	def test_multiple_intervals_and_break(self):
		self.doc["weekly_hours"].insert(1, dict(weekday="Monday", day_status="Open", start_time="13:00", end_time="16:00"))
		self.validate()
		self.assertFalse(self.read("2026-10-12T12:30")["hours"]["within_hours"])
		self.assertTrue(self.read("2026-10-12T13:00")["hours"]["within_hours"])

	def test_invalid_times_incomplete_and_overnight_are_rejected(self):
		for start, end in ((None, "12:00"), ("8:0", "12:00"), ("24:00", "12:00"), ("08:99", "12:00"),
			("8:00:00.5", "12:00"), ("8:00:00+00:00", "12:00"),
			("08:00", "08:00"), ("22:00", "02:00"), (time(8, tzinfo=timezone.utc), time(12))):
			with self.subTest(start=start, end=end):
				self.doc = configuration()
				self.doc["weekly_hours"][0].update(start_time=start, end_time=end)
				with self.assertRaises(office.ConfigurationError):
					self.validate()
				self.assertEqual(self.read(DAY)["hours"]["status"], "Unavailable")

	def test_frappe_timedelta_and_midnight_times(self):
		self.doc["weekly_hours"][0].update(start_time=timedelta(0), end_time=timedelta(hours=1))
		self.validate()
		self.assertTrue(self.read("2026-10-12T00:00")["hours"]["within_hours"])
		for invalid in (timedelta(days=1), timedelta(seconds=-1), timedelta(microseconds=1)):
			with self.assertRaises(office.ConfigurationError):
				office._time(invalid)

	def test_saved_times_survive_frappe_json_roundtrip(self):
		import frappe

		self.doc["weekly_hours"][0].update(start_time=timedelta(hours=8), end_time=timedelta(hours=12))
		exception(self.doc, kind="Exceptional Hours", status="Open")
		self.doc["exception_hours"] = [dict(exception_date=DAY, start_time=timedelta(0), end_time=timedelta(hours=1))]
		self.doc = frappe.parse_json(frappe.as_json(self.doc))
		self.validate()
		self.assertTrue(self.read("2026-10-12T00:00")["hours"]["within_hours"])
		self.assertFalse(self.read("2026-10-12T01:00")["hours"]["within_hours"])
		self.doc["calendar_exceptions"] = []
		self.doc["exception_hours"] = []
		self.assertTrue(self.read("2026-10-12T08:00")["hours"]["within_hours"])
		self.assertFalse(self.read("2026-10-12T12:00")["hours"]["within_hours"])

	def test_single_digit_hours_with_optional_seconds(self):
		for start, end in (("8:00", "9:00"), ("8:00:00", "09:00:00")):
			with self.subTest(start=start, end=end):
				self.doc["weekly_hours"][0].update(start_time=start, end_time=end)
				self.validate()
				self.assertTrue(self.read("2026-10-12T08:00")["hours"]["within_hours"])
				self.assertFalse(self.read("2026-10-12T09:00")["hours"]["within_hours"])

	def test_duplicates_overlaps_and_reversed_order(self):
		for start, end in (("08:00", "12:00"), ("11:00", "13:00"), ("07:00", "08:00")):
			self.doc = configuration()
			self.doc["weekly_hours"].insert(1, dict(weekday="Monday", day_status="Open", start_time=start, end_time=end))
			with self.assertRaises(office.ConfigurationError):
				self.validate()

	def test_incomplete_week_invalid_day_and_closed_contradictions(self):
		base = configuration()
		cases = [base["weekly_hours"][:-1], list(reversed(base["weekly_hours"])),
			[dict(weekday="Unknown", day_status="Open")],
			[dict(weekday="Monday", day_status="Closed"), *base["weekly_hours"]]]
		closed_with_time = copy.deepcopy(base["weekly_hours"])
		closed_with_time[-1]["start_time"] = "00:00"
		cases.append(closed_with_time)
		for rows in cases:
			self.doc["weekly_hours"] = rows
			with self.assertRaises(office.ConfigurationError):
				self.validate()

	def test_holiday_closure_takes_precedence_without_internal_reason(self):
		exception(self.doc, internal_reason="PRIVATE-CONCILIATION")
		self.validate()
		result = self.read("2026-10-12T09:00")
		self.assertTrue(result["hours"]["closed"])
		self.assertIsNone(result["hours"]["public_reason"])
		self.assertNotIn("PRIVATE-CONCILIATION", str(result))
		self.assertNotIn("internal_reason", str(result))
		self.assertNotIn("Holiday", str(result))

	def test_private_reason_never_becomes_public_fallback(self):
		exception(self.doc, kind="Extraordinary Closure", internal_reason="PRIVATE")
		self.assertIsNone(self.read(DAY)["hours"]["public_reason"])

	def test_exceptional_hours_open_closed_weekend_and_replace_ordinary_hours(self):
		exception(self.doc, date(2026, 10, 17), kind="Exceptional Hours", status="Open")
		self.doc["exception_hours"] = [dict(exception_date="2026-10-17", start_time="10:00", end_time="11:00")]
		self.validate()
		self.assertTrue(self.read("2026-10-17T10:00")["hours"]["within_hours"])
		self.doc["calendar_exceptions"][0].update(exception_date=DAY, exception_type="Exceptional Hours")
		self.doc["exception_hours"][0]["exception_date"] = DAY
		self.assertFalse(self.read("2026-10-12T08:00")["hours"]["within_hours"])

	def test_exception_works_without_weekly_information(self):
		self.doc["weekly_hours"] = []
		exception(self.doc, kind="Extraordinary Closure")
		self.validate()
		self.assertEqual(self.read(DAY)["hours"]["status"], "Available")
		self.assertEqual(self.read(date(2026, 10, 13))["hours"]["status"], "Unavailable")

	def test_duplicate_and_conflicting_exceptions(self):
		exception(self.doc)
		exception(self.doc, kind="Exceptional Hours", status="Open")
		with self.assertRaises(office.ConfigurationError):
			self.validate()
		self.assertEqual(self.read(DAY)["hours"]["status"], "Unavailable")

	def test_exception_dates_effects_missing_and_orphan_intervals(self):
		cases = [dict(exception_date="2026-02-30", exception_type="Holiday", day_status="Closed"),
			dict(exception_date=DAY, exception_type="Holiday", day_status="Open"),
			dict(exception_date=DAY, exception_type="Exceptional Hours", day_status="Closed"),
			dict(exception_date=DAY, exception_type="Exceptional Hours", day_status="Open")]
		for row in cases:
			self.doc["calendar_exceptions"] = [row]
			with self.assertRaises(office.ConfigurationError):
				self.validate()
		self.doc["calendar_exceptions"] = []
		self.doc["exception_hours"] = [dict(exception_date=DAY, start_time="08:00", end_time="12:00")]
		with self.assertRaises(office.ConfigurationError):
			self.validate()

	def test_exception_multiple_intervals_overlap_and_closed_intervals(self):
		exception(self.doc, kind="Exceptional Hours", status="Open")
		self.doc["exception_hours"] = [dict(exception_date=DAY, start_time="08:00", end_time="10:00"),
			dict(exception_date=DAY, start_time="11:00", end_time="12:00")]
		with self.assertRaises(office.ConfigurationError):
			self.validate()
		self.assertEqual(self.read(DAY)["hours"]["reason_code"], "invalid_configuration")
		self.doc["exception_hours"][1]["start_time"] = "09:00"
		with self.assertRaises(office.ConfigurationError):
			self.validate()
		self.doc["calendar_exceptions"][0].update(exception_type="Holiday", day_status="Closed")
		with self.assertRaises(office.ConfigurationError):
			self.validate()

	def test_approved_types_require_internal_reason_and_reject_public_reason(self):
		for kind in ("Exceptional Hours", "Extraordinary Closure"):
			self.doc = configuration()
			exception(self.doc, kind=kind, status="Open" if kind == "Exceptional Hours" else "Closed", internal_reason="  ")
			with self.assertRaisesRegex(office.ConfigurationError, "internal reason"):
				self.validate()
		for kind in ("Holiday", "Exceptional Hours", "Extraordinary Closure"):
			self.doc = configuration()
			exception(self.doc, kind=kind, status="Open" if kind == "Exceptional Hours" else "Closed", public_reason="PRIVATE-PUBLIC-ATTEMPT")
			with self.assertRaisesRegex(office.ConfigurationError, "Public reason must be empty"):
				self.validate()
			self.assertNotIn("PRIVATE-PUBLIC-ATTEMPT", str(self.read(DAY)))

	def test_removed_types_are_rejected_for_every_state(self):
		for kind in ("Administrative Meeting", "Special Day"):
			for status in ("Open", "Closed"):
				self.doc = configuration()
				exception(self.doc, kind=kind, status=status)
				with self.assertRaises(office.ConfigurationError):
					self.validate()

	def test_holiday_needs_only_date_type_and_automatic_status(self):
		exception(self.doc)
		self.validate()
		self.assertTrue(self.read(DAY)["hours"]["closed"])
		self.assertEqual(self.doc["exception_hours"], [])

	def test_honduras_aware_naive_and_transition_between_days(self):
		self.assertTrue(self.read(datetime(2026, 10, 12, 14, tzinfo=timezone.utc))["hours"]["within_hours"])
		self.assertEqual(self.read(datetime(2026, 10, 12, 5, 59, tzinfo=timezone.utc))["date"], "2026-10-11")
		self.assertEqual(self.read(datetime(2026, 10, 12, 6, tzinfo=timezone.utc))["date"], "2026-10-12")
		self.assertEqual(office.local_datetime(datetime(2026, 10, 12, 8)).hour, 8)

	def test_current_time_uses_frappe_institutional_timezone(self):
		with patch("frappe.utils.get_datetime_in_timezone", return_value=datetime(2026, 10, 12, 14, tzinfo=timezone.utc)) as clock:
			self.assertEqual(office.local_datetime().hour, 8)
			clock.assert_called_once_with(office.TIMEZONE)

	def test_location_text_references_and_optional_map(self):
		self.doc["office_locations"] = [location(references="Synthetic landmark")]
		self.validate()
		result = self.read(DAY)["location"]
		self.assertEqual(result["status"], "Available")
		self.assertEqual(result["references"], "Synthetic landmark")
		self.assertIsNone(result["google_maps_url"])

	def test_unapproved_location_or_map_is_not_published(self):
		self.doc["office_locations"] = [location(google_maps_url="https://www.google.com/maps", maps_verified=0)]
		self.assertIsNone(self.read(DAY)["location"]["google_maps_url"])
		self.doc["office_locations"][0]["maps_verified"] = 1
		self.assertEqual(self.read(DAY)["location"]["google_maps_url"], "https://www.google.com/maps")
		self.doc["office_locations"][0]["publication_approved"] = 0
		self.assertIsNone(self.read(DAY)["location"]["address"])

	def test_map_structure_and_verification_require_link(self):
		for url in ("http://maps.google.com/", "https://evil.invalid/maps", "https://www.google.com.evil.invalid/maps", "https://www.google.com/search", "https://user@maps.google.com/", "https://maps.google.com:443/", "https://maps.app.goo.gl/", "https://maps.google.com/\nmalicious"):
			with self.assertRaises(office.ConfigurationError):
				office._maps(url)
		for url in ("https://www.google.com/maps/place/test", "https://maps.google.com/?q=test", "https://maps.app.goo.gl/Test", "https://goo.gl/maps/Test"):
			self.assertEqual(office._maps(url), url)
		self.doc["office_locations"] = [location(maps_verified=1)]
		with self.assertRaises(office.ConfigurationError):
			self.validate()

	def test_scheduled_move_resolves_at_local_midnight_without_future_leak(self):
		self.doc["office_locations"] = [location(address="Old synthetic office"), location(date(2026, 10, 14), address="Future synthetic office")]
		self.validate()
		before = self.read("2026-10-14T05:59:59+00:00")
		after = self.read("2026-10-14T06:00:00+00:00")
		self.assertEqual(before["location"]["address"], "Old synthetic office")
		self.assertNotIn("Future synthetic office", str(before))
		self.assertEqual(after["location"]["address"], "Future synthetic office")
		self.assertNotIn("Old synthetic office", str(after))
		self.assertEqual(self.read(date(2026, 10, 11))["location"]["reason_code"], "no_effective_location")

	def test_unapproved_effective_move_does_not_fall_back_to_old_address(self):
		self.doc["office_locations"] = [location(), location(date(2026, 10, 14), address="Unapproved synthetic move", publication_approved=0)]
		self.assertEqual(self.read(date(2026, 10, 14))["location"]["reason_code"], "not_approved")
		self.assertIsNone(self.read(date(2026, 10, 14))["location"]["address"])

	def test_location_conflicts_duplicates_incomplete_and_future_only(self):
		for rows in ([location(), location()], [location(), location(date(2026, 10, 13))],
			[location(date(2026, 10, 13)), location()], [location(address=" ")], [location(day="bad")],
			[location(date(2026, 10, 13))]):
			self.doc["office_locations"] = rows
			with self.assertRaises(office.ConfigurationError):
				self.validate()

	def test_invalid_location_is_unavailable_without_hiding_valid_hours(self):
		self.doc["office_locations"] = [location(day="bad")]
		self.assertEqual(self.read(DAY)["location"]["reason_code"], "invalid_configuration")
		self.assertEqual(self.read(DAY)["hours"]["status"], "Available")

	def test_common_reader_consistency_and_unavailable_denial(self):
		import frappe
		with patch.object(frappe, "get_doc", return_value=self.doc) as loader:
			for at in ("2026-10-12T08:00", "2026-10-12T12:00", "2026-10-17T08:00"):
				self.assertEqual(office.is_within_office_hours(at)["within_hours"], office.office_information(at)["hours"]["within_hours"])
			loader.assert_called_with(office.SETTINGS)
		with patch.object(frappe, "get_doc", return_value={}):
			self.assertEqual(office.is_within_office_hours("2026-10-12T08:00")["status"], "Unavailable")
			self.assertFalse(office.is_within_office_hours("2026-10-12T08:00")["within_hours"])


if __name__ == "__main__":
	unittest.main()
