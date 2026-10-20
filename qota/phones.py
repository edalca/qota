"""International telephone contracts shared by capture, migration and recipients."""

import re
from dataclasses import dataclass
from functools import lru_cache

import phonenumbers as pn
import pycountry
from babel import Locale


class PhoneError(ValueError):
	"""A closed diagnostic code, never containing a supplied telephone."""


@dataclass(frozen=True)
class Telephone:
	region: str
	national: str
	e164: str


@lru_cache(maxsize=1)
def supported_regions():
	return frozenset(pn.SUPPORTED_REGIONS) & frozenset(c.alpha_2 for c in pycountry.countries)


def validate_region(region):
	if not isinstance(region, str) or region not in supported_regions():
		raise PhoneError("missing_region" if not region else "unsupported_region")
	return region


def validate_phone(region, national):
	"""Accept only a complete national significant number for the selected ISO region."""
	validate_region(region)
	if not isinstance(national, str) or not re.fullmatch(r"[0-9]{1,15}", national):
		raise PhoneError("invalid_national")
	try:
		number = pn.parse(national, region, keep_raw_input=True)
	except pn.NumberParseException:
		raise PhoneError("invalid_national") from None
	if number.extension or number.country_code_source != pn.CountryCodeSource.FROM_DEFAULT_COUNTRY:
		raise PhoneError("international_in_national")
	if not pn.is_possible_number(number):
		raise PhoneError("impossible_length")
	if not pn.is_valid_number(number) or not pn.is_valid_number_for_region(number, region):
		raise PhoneError("invalid_for_region")
	canonical = pn.national_significant_number(number)
	# Requiring the significant national number prevents silently stripping a trunk prefix.
	if canonical != national:
		raise PhoneError("noncanonical_national")
	e164 = pn.format_number(number, pn.PhoneNumberFormat.E164)
	if not re.fullmatch(r"\+[0-9]{1,15}", e164):
		raise PhoneError("invalid_e164")
	reparsed = pn.parse(e164, None)
	if pn.national_significant_number(reparsed) != national or not pn.is_valid_number_for_region(reparsed, region):
		raise PhoneError("round_trip")
	return Telephone(region, canonical, e164)


def international_number(raw):
	"""Validate an explicit international number without inferring an administrative region."""
	if not isinstance(raw, str) or not re.fullmatch(r"\+[0-9 ()-]{1,40}", raw):
		raise PhoneError("not_explicit_international")
	try:
		number = pn.parse(raw, None)
	except pn.NumberParseException:
		raise PhoneError("invalid_e164") from None
	if number.extension or not pn.is_valid_number(number):
		raise PhoneError("invalid_e164")
	return number


def validate_international_for_region(region, raw):
	"""An explicit operator-selected region can resolve a shared international calling code."""
	number = international_number(raw)
	result = validate_phone(region, pn.national_significant_number(number))
	if result.e164 != pn.format_number(number, pn.PhoneNumberFormat.E164):
		raise PhoneError("invalid_for_region")
	return result


def explicit_international(raw):
	"""Derive only a valid, unambiguous explicitly international historical value."""
	number = international_number(raw)
	regions = [r for r in pn.region_codes_for_country_code(number.country_code)
		if r in supported_regions() and pn.is_valid_number_for_region(number, r)]
	if len(regions) != 1:
		raise PhoneError("ambiguous_region")
	return validate_phone(regions[0], pn.national_significant_number(number))


def stored_phone(row, legacy="primary_phone", region="primary_phone_region", national=None, e164="primary_phone_e164"):
	"""Validate stored evidence afresh; a derived column is never the authority."""
	national_value = row.get(national) if national else None
	raw = national_value or row.get(legacy)
	if not raw:
		raise PhoneError("missing_phone")
	selected = row.get(region)
	if national is not None and isinstance(raw, str) and raw.startswith("+"):
		parsed = validate_international_for_region(selected, raw)
	else:
		parsed = validate_phone(selected, raw)
	legacy_value = row.get(legacy)
	if national_value and legacy_value:
		legacy_e164 = pn.format_number(international_number(legacy_value), pn.PhoneNumberFormat.E164) if legacy_value.startswith("+") else validate_phone(selected, legacy_value).e164
		if legacy_e164 != parsed.e164:
			raise PhoneError("inconsistent_legacy")
	if row.get(e164) and row.get(e164) != parsed.e164:
		raise PhoneError("inconsistent_e164")
	return parsed


def region_catalog(language="en"):
	try:
		locale = Locale.parse((language or "en").replace("-", "_"))
	except (ValueError, TypeError):
		locale = Locale.parse("en")
	return sorted([dict(value=r, label=f"{locale.territories.get(r, pycountry.countries.get(alpha_2=r).name)} (+{pn.country_code_for_region(r)})")
		for r in supported_regions()], key=lambda row: row["label"])
