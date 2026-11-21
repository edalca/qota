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

	def validate(self):
		office.validate_configuration(self.doc, today=DAY)

	def test_empty_configuration_is_valid(self):
		office.validate_configuration({}, today=DAY)

	def test_standard_week_is_accepted(self):
		self.validate()
		self.assertEqual([row["weekday"] for row in self.doc["weekly_hours"]], list(office.WEEKDAYS))

	def test_multiple_nonoverlapping_intervals_are_accepted(self):
		self.doc["weekly_hours"].insert(1, dict(weekday="Monday", day_status="Open", start_time="13:00", end_time="16:00"))
		self.validate()
		monday = [row for row in self.doc["weekly_hours"] if row["weekday"] == "Monday"]
		self.assertEqual([(row["start_time"], row["end_time"]) for row in monday], [("08:00", "12:00"), ("13:00", "16:00")])

	def test_invalid_times_incomplete_and_overnight_are_rejected(self):
		for start, end in ((None, "12:00"), ("8:0", "12:00"), ("24:00", "12:00"), ("08:99", "12:00"),
			("8:00:00.5", "12:00"), ("8:00:00+00:00", "12:00"),
			("08:00", "08:00"), ("22:00", "02:00"), (time(8, tzinfo=timezone.utc), time(12))):
			with self.subTest(start=start, end=end):
				self.doc = configuration()
				self.doc["weekly_hours"][0].update(start_time=start, end_time=end)
				with self.assertRaises(office.ConfigurationError):
					self.validate()

	def test_frappe_timedelta_and_midnight_times(self):
		self.doc["weekly_hours"][0].update(start_time=timedelta(0), end_time=timedelta(hours=1))
		self.validate()
		self.assertEqual(office._time(self.doc["weekly_hours"][0]["start_time"]), time(0, 0))
		self.assertEqual(office._time(self.doc["weekly_hours"][0]["end_time"]), time(1, 0))
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
		self.assertEqual(office._time(self.doc["exception_hours"][0]["start_time"]), time(0, 0))
		self.assertEqual(office._time(self.doc["weekly_hours"][0]["start_time"]), time(8, 0))
		self.doc["calendar_exceptions"] = []
		self.doc["exception_hours"] = []
		self.validate()
		self.assertEqual(office._time(self.doc["weekly_hours"][0]["end_time"]), time(12, 0))

	def test_single_digit_hours_with_optional_seconds(self):
		for start, end in (("8:00", "9:00"), ("8:00:00", "09:00:00")):
			with self.subTest(start=start, end=end):
				self.doc = configuration()
				self.doc["weekly_hours"][0].update(start_time=start, end_time=end)
				self.validate()
				self.assertEqual(office._time(self.doc["weekly_hours"][0]["start_time"]), time(8, 0))
				self.assertEqual(office._time(self.doc["weekly_hours"][0]["end_time"]), time(9, 0))

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

	def test_holiday_accepts_an_internal_reason_without_a_public_reason(self):
		exception(self.doc, internal_reason="PRIVATE-CONCILIATION")
		self.validate()
		row = self.doc["calendar_exceptions"][0]
		self.assertEqual(row["internal_reason"], "PRIVATE-CONCILIATION")
		self.assertTrue(row.get("public_reason") in (None, ""))

	def test_extraordinary_closure_keeps_its_reason_on_the_row(self):
		exception(self.doc, kind="Extraordinary Closure", internal_reason="PRIVATE")
		self.validate()
		row = self.doc["calendar_exceptions"][0]
		self.assertEqual(row["exception_type"], "Extraordinary Closure")
		self.assertEqual(row["day_status"], "Closed")
		self.assertEqual(row["internal_reason"], "PRIVATE")
		self.assertTrue(row.get("public_reason") in (None, ""))

	def test_exceptional_hours_accept_a_single_replacement_interval(self):
		exception(self.doc, date(2026, 10, 17), kind="Exceptional Hours", status="Open")
		self.doc["exception_hours"] = [dict(exception_date="2026-10-17", start_time="10:00", end_time="11:00")]
		self.validate()
		self.doc["calendar_exceptions"][0].update(exception_date=DAY, exception_type="Exceptional Hours")
		self.doc["exception_hours"][0]["exception_date"] = DAY
		self.validate()

	def test_exception_works_without_weekly_information(self):
		self.doc["weekly_hours"] = []
		exception(self.doc, kind="Extraordinary Closure")
		self.validate()
		self.assertEqual(self.doc["weekly_hours"], [])
		self.assertEqual(len(self.doc["calendar_exceptions"]), 1)

	def test_duplicate_and_conflicting_exceptions(self):
		exception(self.doc)
		exception(self.doc, kind="Exceptional Hours", status="Open")
		with self.assertRaises(office.ConfigurationError):
			self.validate()

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
		self.assertEqual(self.doc["calendar_exceptions"][0]["day_status"], "Closed")
		self.assertEqual(self.doc["exception_hours"], [])

	def test_honduras_aware_naive_and_transition_between_days(self):
		self.assertEqual(office.local_datetime(datetime(2026, 10, 12, 14, tzinfo=timezone.utc)).hour, 8)
		self.assertEqual(office.local_datetime(datetime(2026, 10, 12, 5, 59, tzinfo=timezone.utc)).date(), date(2026, 10, 11))
		self.assertEqual(office.local_datetime(datetime(2026, 10, 12, 6, tzinfo=timezone.utc)).date(), date(2026, 10, 12))
		self.assertEqual(office.local_datetime(datetime(2026, 10, 12, 8)).hour, 8)

	def test_current_time_uses_frappe_institutional_timezone(self):
		with patch("frappe.utils.get_datetime_in_timezone", return_value=datetime(2026, 10, 12, 14, tzinfo=timezone.utc)) as clock:
			self.assertEqual(office.local_datetime().hour, 8)
			clock.assert_called_once_with(office.TIMEZONE)

	def test_location_text_references_and_optional_map(self):
		self.doc["office_locations"] = [location(references="Synthetic landmark")]
		self.validate()
		row = self.doc["office_locations"][0]
		self.assertEqual(row["references"], "Synthetic landmark")
		self.assertNotIn("google_maps_url", row)

	def test_unapproved_or_unverified_location_remains_valid(self):
		self.doc["office_locations"] = [location(google_maps_url="https://www.google.com/maps", maps_verified=0)]
		self.validate()
		self.doc["office_locations"][0]["maps_verified"] = 1
		self.validate()
		self.doc["office_locations"][0]["publication_approved"] = 0
		self.validate()
		row = self.doc["office_locations"][0]
		self.assertEqual(row["google_maps_url"], "https://www.google.com/maps")
		self.assertEqual(row["publication_approved"], 0)

	def test_map_structure_and_verification_require_link(self):
		for url in ("http://maps.google.com/", "https://evil.invalid/maps", "https://www.google.com.evil.invalid/maps", "https://www.google.com/search", "https://user@maps.google.com/", "https://maps.google.com:443/", "https://maps.app.goo.gl/", "https://maps.google.com/\nmalicious"):
			with self.assertRaises(office.ConfigurationError):
				office._maps(url)
		for url in ("https://www.google.com/maps/place/test", "https://maps.google.com/?q=test", "https://maps.app.goo.gl/Test", "https://goo.gl/maps/Test"):
			self.assertEqual(office._maps(url), url)
		self.doc["office_locations"] = [location(maps_verified=1)]
		with self.assertRaises(office.ConfigurationError):
			self.validate()

	def test_scheduled_move_requires_a_current_location_before_a_future_one(self):
		self.doc["office_locations"] = [location(address="Old synthetic office"), location(date(2026, 10, 14), address="Future synthetic office")]
		self.validate()
		self.assertEqual([row["address"] for row in self.doc["office_locations"]], ["Old synthetic office", "Future synthetic office"])

	def test_unapproved_future_location_remains_a_valid_schedule(self):
		self.doc["office_locations"] = [location(), location(date(2026, 10, 14), address="Unapproved synthetic move", publication_approved=0)]
		self.validate()
		self.assertEqual(self.doc["office_locations"][1]["publication_approved"], 0)

	def test_location_conflicts_duplicates_incomplete_and_future_only(self):
		for rows in ([location(), location()], [location(), location(date(2026, 10, 13))],
			[location(date(2026, 10, 13)), location()], [location(address=" ")], [location(day="bad")],
			[location(date(2026, 10, 13))]):
			self.doc["office_locations"] = rows
			with self.assertRaises(office.ConfigurationError):
				self.validate()

	def test_invalid_location_is_rejected(self):
		self.doc["office_locations"] = [location(day="bad")]
		with self.assertRaises(office.ConfigurationError):
			self.validate()


if __name__ == "__main__":
	unittest.main()
