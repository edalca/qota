# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""Institutional office calendar validation, without transport.

Naive explicit datetimes mean institutional local time, never server time. Aware
values are converted to Honduras. Intervals include opening and exclude closing;
overnight intervals are rejected. Locations become effective at local midnight.
The native settings controller uses these validators without integration dependencies.
"""

import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SETTINGS = "Institutional Settings"
TIMEZONE = "America/Tegucigalpa"
LOCAL_ZONE = ZoneInfo(TIMEZONE)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
EXCEPTION_TYPES = {"Holiday", "Exceptional Hours", "Extraordinary Closure"}


class ConfigurationError(ValueError):
	"""An incomplete or contradictory institutional configuration."""


def _text(value):
	return str(value or "").strip()


def _date(value):
	if isinstance(value, date) and not isinstance(value, datetime):
		return value
	if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
		try:
			return date.fromisoformat(value)
		except ValueError:
			pass
	raise ConfigurationError("Institutional dates must be valid dates in YYYY-MM-DD format.")


def _time(value):
	if isinstance(value, timedelta):
		seconds = value.total_seconds()
		if 0 <= seconds < 86400 and seconds.is_integer():
			return (datetime.min + value).time()
	elif isinstance(value, time) and value.tzinfo is None and value.microsecond == 0:
		return value
	# Frappe serializes MariaDB Time values with an unpadded hour (e.g. 8:00:00).
	elif isinstance(value, str) and re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", value):
		try:
			parts = [int(part) for part in value.split(":")]
			return time(*parts)
		except ValueError:
			pass
	raise ConfigurationError("Office times must be valid local times in H:MM or H:MM:SS format (one or two hour digits).")


def _interval(row):
	start, end = _time(row.get("start_time")), _time(row.get("end_time"))
	if start >= end:
		raise ConfigurationError("Opening time must precede closing time. Overnight intervals are not supported.")
	return start, end


def _check_intervals(intervals):
	for previous, current in zip(intervals, intervals[1:]):
		if previous[1] > current[0]:
			raise ConfigurationError("Office intervals must be chronological, without duplicates or overlaps.")


def _weekly(doc):
	rows = doc.get("weekly_hours") or []
	if not rows:
		return None
	result = {day: [] for day in WEEKDAYS}
	statuses = {}
	last_day = -1
	for row in rows:
		day, status = row.get("weekday"), row.get("day_status")
		if day not in WEEKDAYS or status not in {"Open", "Closed"}:
			raise ConfigurationError("Every weekly row requires a valid weekday and an explicit Open or Closed status.")
		index = WEEKDAYS.index(day)
		if index < last_day:
			raise ConfigurationError("Weekly days must be ordered from Monday to Sunday.")
		last_day = index
		if day in statuses and (status == "Closed" or statuses[day] != status):
			raise ConfigurationError("A closed weekday must have exactly one row and cannot also be open.")
		statuses[day] = status
		if status == "Closed":
			if row.get("start_time") not in (None, "") or row.get("end_time") not in (None, ""):
				raise ConfigurationError("Closed days must not contain office intervals.")
		else:
			result[day].append(_interval(row))
	if len(statuses) != 7:
		raise ConfigurationError("A configured weekly schedule must explicitly include all seven weekdays.")
	for intervals in result.values():
		_check_intervals(intervals)
	return result


def _exceptions(doc):
	result = {}
	previous = None
	for row in doc.get("calendar_exceptions") or []:
		day = _date(row.get("exception_date"))
		if day in result or (previous is not None and day < previous):
			raise ConfigurationError("Calendar exceptions must have unique dates in chronological order.")
		previous = day
		kind, status = row.get("exception_type"), row.get("day_status")
		if kind not in EXCEPTION_TYPES or status not in {"Open", "Closed"}:
			raise ConfigurationError("Every calendar exception requires a valid type and an explicit Open or Closed status.")
		if kind in {"Holiday", "Extraordinary Closure"} and status != "Closed":
			raise ConfigurationError("Holidays and extraordinary closures must be Closed.")
		if kind == "Exceptional Hours" and status != "Open":
			raise ConfigurationError("Exceptional hours must be Open with one replacement interval.")
		if kind != "Holiday" and not _text(row.get("internal_reason")):
			raise ConfigurationError("Exceptional hours and extraordinary closures require an internal reason.")
		if row.get("public_reason") not in (None, ""):
			raise ConfigurationError("Calendar exception reasons are internal only. Public reason must be empty.")
		# Keep the public contract key empty; no exception reason is publishable.
		result[day] = {"status": status, "public_reason": None, "intervals": []}
	previous = None
	for row in doc.get("exception_hours") or []:
		day = _date(row.get("exception_date"))
		if previous is not None and day < previous:
			raise ConfigurationError("Exceptional intervals must be ordered by date and opening time.")
		previous = day
		if day not in result or result[day]["status"] != "Open":
			raise ConfigurationError("Exceptional intervals require an Open calendar exception on the same date.")
		result[day]["intervals"].append(_interval(row))
	for exception in result.values():
		if exception["status"] == "Open" and len(exception["intervals"]) != 1:
			raise ConfigurationError("Exceptional hours require exactly one replacement interval.")
		_check_intervals(exception["intervals"])
	return result


def _check(value):
	if value not in (None, "", 0, 1, "0", "1"):
		raise ConfigurationError("Institutional publication confirmations must be explicit check values.")
	return value in (1, "1")


def _maps(value):
	url = _text(value)
	if not url:
		return None
	try:
		parts = urlsplit(url)
		valid = parts.scheme == "https" and not parts.username and not parts.password and parts.port is None
		valid = valid and not re.search(r"\s|[\x00-\x1f\x7f]", url)
		if parts.hostname in {"google.com", "www.google.com"}:
			valid = valid and (parts.path == "/maps" or parts.path.startswith("/maps/"))
		elif parts.hostname == "maps.google.com":
			valid = valid and bool(parts.path or parts.query)
		elif parts.hostname == "maps.app.goo.gl":
			valid = valid and bool(parts.path.strip("/"))
		elif parts.hostname == "goo.gl":
			valid = valid and parts.path.startswith("/maps/") and bool(parts.path[6:])
		else:
			valid = False
		if valid:
			return url
	except ValueError:
		pass
	raise ConfigurationError("Use an HTTPS Google Maps link without credentials, custom ports or other destinations.")


def _locations(doc):
	result, addresses = [], set()
	for row in doc.get("office_locations") or []:
		day, address = _date(row.get("effective_from")), _text(row.get("address"))
		if not address:
			raise ConfigurationError("Every office location requires an official address and an effective date.")
		if result and day <= result[-1]["effective_from"]:
			raise ConfigurationError("Office locations must have unique effective dates in chronological order.")
		key = " ".join(address.casefold().split())
		if key in addresses:
			raise ConfigurationError("Office locations must not duplicate an address.")
		addresses.add(key)
		url = _maps(row.get("google_maps_url"))
		verified = _check(row.get("maps_verified"))
		if verified and not url:
			raise ConfigurationError("A verified Google Maps link requires a configured link.")
		result.append({"effective_from": day, "address": address, "references": _text(row.get("references")) or None,
			"publication_approved": _check(row.get("publication_approved")), "google_maps_url": url if verified else None})
	return result


def local_datetime(value=None):
	"""Resolve an instant in Honduras; naive inputs explicitly mean local time."""
	if value is None:
		from frappe.utils import get_datetime_in_timezone
		value = get_datetime_in_timezone(TIMEZONE)
	if isinstance(value, str):
		value = datetime.fromisoformat(value)
	if not isinstance(value, datetime):
		raise ValueError("An explicit datetime is required.")
	return value.replace(tzinfo=LOCAL_ZONE) if value.tzinfo is None else value.astimezone(LOCAL_ZONE)


def validate_configuration(doc, *, today=None):
	"""Validate administrative data without assigning institutional defaults."""
	_weekly(doc)
	_exceptions(doc)
	locations = _locations(doc)
	current = _date(today) if today is not None else local_datetime().date()
	if locations and locations[0]["effective_from"] > current:
		raise ConfigurationError("Record a current office location before scheduling a future move.")
