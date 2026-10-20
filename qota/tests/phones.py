"""Pure international telephone contracts using library examples only."""

import unittest

import phonenumbers as pn

from qota.phones import PhoneError, explicit_international, region_catalog, stored_phone, validate_phone, validate_international_for_region


def example(region, kind=pn.PhoneNumberType.MOBILE):
	return pn.national_significant_number(pn.example_number_for_type(region, kind))


class TelephoneTests(unittest.TestCase):
	def test_supported_countries_round_trip_fixed_mobile_and_italian_zero(self):
		for region in ("HN", "MX", "US", "CA", "GB", "IM", "IT", "DE", "BR", "AU"):
			for kind in (pn.PhoneNumberType.FIXED_LINE, pn.PhoneNumberType.MOBILE):
				with self.subTest(region=region, kind=kind):
					national = example(region, kind)
					result = validate_phone(region, national)
					self.assertEqual(pn.national_significant_number(pn.parse(result.e164, None)), national)
					self.assertEqual(result.national, national)
		self.assertTrue(validate_phone("IT", example("IT", pn.PhoneNumberType.FIXED_LINE)).national.startswith("0"))

	def test_invalid_national_inputs_never_cleaned_or_truncated(self):
		for raw in ("123456789", "1", "0", "00000000", "", None, 1234,
			"１２３４５６７８", "١٢٣٤٥٦٧٨", "9895 8652", "9895-8652", "+50498958652",
			"98958652x1", "98958652 ext 1", "(98958652)", "98958652\n", "0050498958652"):
			with self.subTest(raw=raw), self.assertRaises(PhoneError):
				validate_phone("HN", raw)

	def test_missing_unknown_lowercase_and_special_regions_rejected(self):
		for region in (None, "", "ZZ", "hn", "HND", "AC", "TA", "XK"):
			with self.subTest(region=region), self.assertRaises(PhoneError):
				validate_phone(region, example("HN"))

	def test_shared_calling_codes_require_selected_region(self):
		for expected, wrong in (("US", "CA"), ("CA", "US"), ("IM", "GB")):
			with self.subTest(expected=expected), self.assertRaises(PhoneError):
				validate_phone(wrong, example(expected, pn.PhoneNumberType.FIXED_LINE))

	def test_variable_national_lengths(self):
		self.assertNotEqual(len(example("DE", pn.PhoneNumberType.FIXED_LINE)), len(example("DE")))
		for kind in (pn.PhoneNumberType.FIXED_LINE, pn.PhoneNumberType.MOBILE):
			validate_phone("DE", example("DE", kind))

	def test_stored_consistency_and_missing_phone(self):
		r = validate_phone("HN", example("HN"))
		row = dict(primary_phone=r.national, primary_phone_region=r.region, primary_phone_e164=r.e164)
		self.assertEqual(stored_phone(row), r)
		with self.assertRaisesRegex(PhoneError, "inconsistent_e164"):
			stored_phone(dict(row, primary_phone_e164="+12015550123"))
		with self.assertRaisesRegex(PhoneError, "missing_region"):
			stored_phone(dict(row, primary_phone_region=None))
		with self.assertRaisesRegex(PhoneError, "missing_phone"):
			stored_phone({})

	def test_explicit_historical_presentation_and_no_inference(self):
		r = validate_phone("HN", example("HN"))
		self.assertEqual(explicit_international(r.e164[:4]+" "+r.national[:4]+"-"+r.national[4:]), r)
		for raw in (r.national, r.e164[1:], "00"+r.e164[1:], r.e164+" ext. 3", "+１２３４"):
			with self.subTest(raw=raw), self.assertRaises(PhoneError):
				explicit_international(raw)

	def test_explicit_region_can_validate_shared_international_without_migration_inference(self):
		for region in ('IT','IM','AU'):
			r = validate_phone(region, example(region))
			self.assertEqual(validate_international_for_region(region, r.e164), r)
		with self.assertRaises(PhoneError):
			validate_international_for_region('CA', validate_phone('US', example('US')).e164)

	def test_catalog_iso_shared_prefix_and_localized_names(self):
		catalog={r['value']:r['label'] for r in region_catalog('es')}
		self.assertEqual(catalog['HN'], 'Honduras (+504)')
		self.assertEqual(catalog['MX'], 'México (+52)')
		self.assertEqual(catalog['US'], 'Estados Unidos (+1)')
		self.assertEqual(catalog['CA'], 'Canadá (+1)')
		self.assertNotIn('AC', catalog)


if __name__ == '__main__':
	unittest.main()
