"""Opt-in local telephone capture and historical-assignment tests; all fixtures roll back."""

from contextlib import ExitStack
import json
import os
import unittest
import uuid
from unittest.mock import patch

import frappe
from frappe.client import insert as api_insert, set_value as api_set_value

from qota.governance import phone_capture as capture
from qota.governance import phone_region_assignment as assignment
from qota.phones import validate_phone
from qota.tests.phones import example


def connect_local():
	site = os.environ.get("QOTA_TEST_SITE", "qota.localhost")
	sites_path = "/home/frappe/frappe-bench/sites"
	frappe.init(site=site, sites_path=sites_path)
	os.chdir(sites_path)
	frappe.connect()
	frappe.set_user("Administrator")


class _Fixtures:
	def __init__(self):
		self.prefix = f"QOTA-PHONE-{uuid.uuid4().hex[:8]}-"
		self.rows = []
		self.ordinary = f"{self.prefix.lower()}user@example.invalid"
		frappe.get_doc(dict(doctype="User", name=self.ordinary, email=self.ordinary,
			first_name="Phone Test", enabled=1, user_type="System User")).db_insert()
		self.rows.append(("User", self.ordinary))

	def insert(self, doctype, **values):
		name = values.pop("name", f"{self.prefix}{uuid.uuid4().hex[:8]}")
		doc = frappe.get_doc(dict(doctype=doctype, name=name, **values))
		doc.db_insert()
		self.rows.append((doctype, doc.name))
		return doc.name

	def clear_fixture_caches(self):
		for doctype, name in self.rows:
			frappe.clear_document_cache(doctype, name)
		frappe.clear_document_cache("Institutional Settings", "Institutional Settings")


class PhoneDatabaseTests(unittest.TestCase):
	def setUp(self):
		frappe.set_user('Administrator')
		frappe.db.rollback()
		self.stack = ExitStack()
		self.stack.enter_context(patch.object(frappe.db, 'commit', lambda: None))
		self.fx = _Fixtures()
		self.addCleanup(self.finish)
		self.number = example('HN')
		self.initial = frappe.get_doc('Institutional Settings').as_dict()

	def finish(self):
		frappe.set_user('Administrator')
		frappe.db.rollback()
		self.fx.clear_fixture_caches()
		self.assertEqual(frappe.get_doc('Institutional Settings').as_dict(), self.initial)
		self.stack.close()

	def new(self, **phone):
		return frappe.get_doc(dict(doctype='Subscriber', subscriber_type='Natural Person',
			full_name=self.fx.prefix+'Person', id_type='Passport', id_number=self.fx.prefix, **phone))

	def historical(self, raw='123456789', region=None, **values):
		return self.fx.insert('Subscriber', subscriber_type='Natural Person', full_name=self.fx.prefix+'Historical',
			id_type='Passport', id_number=self.fx.prefix, primary_phone=raw, primary_phone_region=region, **values)

	def default(self, region):
		doc=frappe.get_doc('Institutional Settings');doc.default_phone_region=region;doc.save()

	def scoped_pending(self, lock=False):
		return frappe.db.sql('''SELECT name, modified, primary_phone, primary_phone_region,
			primary_phone_e164 FROM tabSubscriber WHERE name LIKE %s
			AND COALESCE(primary_phone,'')!=''
			AND COALESCE(primary_phone_region,'')='' ORDER BY name'''+(' FOR UPDATE' if lock else ''),
			(self.fx.prefix+'%',),as_dict=True)

	def test_single_original_field_is_editable_and_obsolete_projection_is_ignored(self):
		meta=frappe.get_meta('Subscriber')
		self.assertFalse(meta.get_field('primary_phone').read_only)
		self.assertIsNone(meta.get_field('primary_phone_national'))
		doc=self.new(primary_phone_region='HN',primary_phone=self.number).insert()
		# Unknown input from the retired representation cannot override the real source.
		doc.set('primary_phone_national','123456789')
		doc.full_name='Synthetic single-field correction';doc.save()
		self.assertEqual(doc.primary_phone,self.number)
		self.assertEqual(doc.primary_phone_e164,validate_phone('HN',self.number).e164)

	def test_new_valid_and_empty_optional_with_region_only(self):
		doc=self.new(primary_phone_region='HN', primary_phone=self.number).insert()
		self.assertEqual(doc.primary_phone, self.number)
		self.assertEqual(doc.primary_phone_e164, validate_phone('HN',self.number).e164)
		for values in ({},dict(primary_phone_region='CA')):
			empty=self.new(**values).insert();self.assertFalse(empty.primary_phone_e164)

	def test_every_save_rejects_historical_invalid_even_unrelated_changes(self):
		name=self.historical(region='HN')
		original=frappe.get_doc('Subscriber',name).as_dict()
		status=capture.inspect_capture('Subscriber',name)
		self.assertEqual(status['status'],'Invalid')
		self.assertEqual(frappe.get_doc('Subscriber',name).as_dict(),original)
		for field,value in [('full_name','Changed synthetic name'),('tax_address','Synthetic address')]:
			with self.subTest(field=field),self.assertRaises(frappe.ValidationError):
				doc=frappe.get_doc('Subscriber',name);doc.set(field,value);doc.save()
		self.assertEqual(frappe.get_doc('Subscriber',name).as_dict(),original)

	def test_historical_missing_region_rejects_even_legacy_unchanged_flags(self):
		name=self.historical(self.number)
		doc=frappe.get_doc('Subscriber',name);doc.flags.legacy=True
		self.assertEqual(capture.inspect_capture('Subscriber',name)['reason_code'],'missing_region')
		with self.assertRaises(frappe.ValidationError):doc.save()

	def test_correct_or_explicitly_clear_historical_phone(self):
		for clear in (False,True):
			name=self.historical(region='HN');doc=frappe.get_doc('Subscriber',name)
			if clear:doc.primary_phone=None
			else:doc.primary_phone=self.number
			doc.save();actual=frappe.get_doc('Subscriber',name)
			self.assertFalse(actual.primary_phone) if clear else self.assertEqual(actual.primary_phone,self.number)
			self.assertEqual(capture.inspect_capture('Subscriber',name)['status'],'Missing' if clear else 'Valid')

	def test_wrong_shared_region_and_changed_region_rejected(self):
		for selected,number in [('US',example('CA')),('CA',example('US')),('HN','123456789')]:
			with self.subTest(selected=selected),self.assertRaises(frappe.ValidationError):
				self.new(primary_phone_region=selected,primary_phone=number).insert()
		doc=self.new(primary_phone_region='US',primary_phone=example('US')).insert()
		doc.primary_phone_region='CA'
		with self.assertRaises(frappe.ValidationError):doc.save()

	def test_backend_api_insert_and_update_cannot_bypass(self):
		with self.assertRaises(frappe.ValidationError):
			api_insert(self.new(primary_phone='123456789',primary_phone_region='HN').as_dict())
		name=self.historical(region='HN')
		with self.assertRaises(frappe.ValidationError):
			api_set_value('Subscriber',name,'full_name','API changed only name')

	def test_import_and_quick_entry_use_same_backend_full_form(self):
		self.assertFalse(frappe.get_meta('Subscriber').quick_entry)
		for importing in (False,True):
			with self.subTest(importing=importing),self.assertRaises(frappe.ValidationError):
				with patch.dict(frappe.flags,{'in_import':importing}):
					if importing:
						from frappe.core.doctype.data_import.importer import Importer
						importer=object.__new__(Importer);importer.doctype='Subscriber';importer._uses_tree_aliases=False
						importer.data_import=frappe._dict(doctype='Data Import',name='Synthetic telephone import')
						importer.insert_record(self.new(primary_phone='123456789',primary_phone_region='HN').as_dict())
					else:
						api_insert(self.new(primary_phone='123456789',primary_phone_region='HN').as_dict())

	def test_client_e164_recalculated_and_omitted_api_fields_preserved(self):
		doc=self.new(primary_phone=self.number,primary_phone_region='HN',primary_phone_e164='+12015550123').insert()
		self.assertEqual(doc.primary_phone_e164,validate_phone('HN',self.number).e164)
		api_set_value('Subscriber',doc.name,'full_name','Updated via sparse API')
		actual=frappe.get_doc('Subscriber',doc.name)
		self.assertEqual(actual.primary_phone,self.number)
		self.assertEqual(actual.primary_phone_e164,doc.primary_phone_e164)

	def test_structured_deletion_preserves_optional_region_and_italian_zeros(self):
		national=example('IT',0)
		doc=self.new(primary_phone_region='IT',primary_phone=national).insert()
		self.assertTrue(doc.primary_phone.startswith('0'))
		doc.primary_phone='';doc.save()
		self.assertFalse(doc.primary_phone);self.assertFalse(doc.primary_phone_e164);self.assertEqual(doc.primary_phone_region,'IT')

	def test_form_read_does_not_modify_historical_metadata(self):
		for raw,region,status in [(None,None,'Missing'),(self.number,'HN','Valid'),(self.number,None,'Invalid'),('123456789','HN','Invalid')]:
			name=self.historical(raw,region);before=frappe.get_doc('Subscriber',name).as_dict()
			self.assertEqual(capture.inspect_capture('Subscriber',name)['status'],status)
			self.assertEqual(frappe.get_doc('Subscriber',name).as_dict(),before)

	def test_new_capture_default_changes_do_not_reinterpret_existing(self):
		name=self.historical();before=frappe.get_doc('Subscriber',name).as_dict()
		self.default('HN');self.assertEqual(capture.capture_options('Subscriber')['default_region'],'HN')
		self.default('MX');self.assertEqual(capture.capture_options('Subscriber')['default_region'],'MX')
		self.assertEqual(frappe.get_doc('Subscriber',name).as_dict(),before)

	def test_assignment_preserves_all_originals_invalids_and_confirmed_regions(self):
		self.default('HN')
		valid=self.historical(self.number)
		invalids=[self.historical('123456789'),self.historical('223456789'),self.historical('323456789')]
		confirmed=self.historical(example('US'),'US')
		before={name:frappe.get_doc('Subscriber',name).as_dict() for name in [valid,*invalids,confirmed]}
		with patch.object(assignment,'_pending',self.scoped_pending),patch('qota.governance.doctype.subscriber.subscriber.Subscriber.save',side_effect=AssertionError('No ordinary saves')):
			review=assignment.preview_assignment();self.assertEqual((review['eligible'],review['valid'],review['invalid']),(4,1,3))
			with self.assertRaises(frappe.ValidationError):assignment.apply_assignment(review['token'],False)
			result=assignment.apply_assignment(review['token'],True)
			self.assertEqual((result['assigned'],result['remaining']),(4,0))
			self.assertTrue(assignment.apply_assignment(review['token'],True)['repeated'])
			self.assertEqual(assignment.preview_assignment()['eligible'],0)
		for name in before:
			actual=frappe.get_doc('Subscriber',name).as_dict();expected=dict(before[name])
			if name!=confirmed:expected['primary_phone_region']='HN'
			self.assertEqual(actual,expected)
		for name in invalids:
			with self.assertRaises(frappe.ValidationError):frappe.get_doc('Subscriber',name).save()
		version=frappe.get_doc('Version','qota-phone-region-'+review['token'])
		self.assertEqual(json.loads(version.data)['phone_region_assignment']['region'],'HN')
		for name in before:self.assertNotIn(name,version.data)
		self.default('CA');self.assertEqual(frappe.db.get_value('Subscriber',valid,'primary_phone_region'),'HN')

	def test_assignment_detects_intervening_operator_region_and_default_changes(self):
		self.default('HN');name=self.historical(self.number)
		with patch.object(assignment,'_pending',self.scoped_pending):
			review=assignment.preview_assignment()
			frappe.db.set_value('Subscriber',name,'primary_phone_region','MX')
			with self.assertRaises(frappe.ValidationError):assignment.apply_assignment(review['token'],True)
			self.assertEqual(frappe.db.get_value('Subscriber',name,'primary_phone_region'),'MX')
			review=assignment.preview_assignment();self.default('CA')
			with self.assertRaises(frappe.ValidationError):assignment.apply_assignment(review['token'],True)

	def test_assignment_failure_rolls_back_and_same_confirmation_recovers(self):
		self.default('HN');names=[self.historical(self.number),self.historical('123456789')]
		with patch.object(assignment,'_pending',self.scoped_pending):
			review=assignment.preview_assignment();frappe.db.savepoint('phone_assignment')
			with patch.object(frappe.model.document.Document,'db_insert',side_effect=RuntimeError('Synthetic interruption')):
				with self.assertRaises(RuntimeError):assignment.apply_assignment(review['token'],True)
			frappe.db.rollback(save_point='phone_assignment')
			self.assertTrue(all(not frappe.db.get_value('Subscriber',n,'primary_phone_region') for n in names))
			self.assertEqual(assignment.apply_assignment(review['token'],True)['assigned'],2)

	def test_configuration_assignment_and_capture_permissions(self):
		self.default('HN')
		sub = self.historical(self.number, 'HN')
		for user in (self.fx.ordinary,'Guest'):
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError):assignment.preview_assignment()
			with self.assertRaises(frappe.PermissionError):assignment.apply_assignment('0'*32,True)
			with self.assertRaises(frappe.PermissionError):capture.capture_options('Institutional Settings')
			with self.assertRaises(frappe.PermissionError):capture.inspect_capture('Subscriber', sub)
			with self.assertRaises(frappe.PermissionError):capture.inspect_capture('Premises', sub)

	def test_installed_schema_unique_single_lengths_and_navigation_translations(self):
		self.assertTrue(frappe.get_meta('Institutional Settings').issingle)
		self.assertFalse(frappe.db.exists('DocType','Governance Settings'))
		self.assertFalse(frappe.get_meta('Institutional Settings').get_field('default_phone_region').default)
		for suffix,length in [('region',2),('e164',16)]:
			f='primary_phone_'+suffix;meta=frappe.get_meta('Subscriber').get_field(f)
			self.assertEqual(meta.length,length);self.assertFalse(meta.unique)
			self.assertTrue(frappe.db.has_column('Subscriber',f))
		menu=frappe.get_doc('Sidebar','Subscribers')
		self.assertEqual(menu.items[-1].label,'Governance Settings');self.assertEqual(menu.items[-1].link_to,'Institutional Settings');self.assertFalse(menu.items[-1].child)
		dock=frappe.get_doc('Dock','qota');item=next(i for i in dock.items if i.link_to=='Subscribers')
		self.assertEqual(item.title,'Governance')
		for lang,expected in [('en','Governance Settings'),('es','Configuración de Gobernanza')]:
			frappe.local.lang=lang;self.assertEqual(frappe._('Institutional Settings'),expected)


def run_local_tests():
	connect_local()
	try:
		result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PhoneDatabaseTests))
		return result.wasSuccessful()
	finally:
		frappe.db.rollback();frappe.destroy()


if __name__=='__main__':
	raise SystemExit(0 if run_local_tests() else 1)
