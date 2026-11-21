"""Historical identity and release inventory contracts without a database."""

import importlib
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.modules.patch_handler import PatchError
from qota import migration_identity

ROOT = Path(__file__).resolve().parents[1]
PATCHES = [line for line in (ROOT / 'patches.txt').read_text().splitlines() if line.startswith('qota.')]
RELEASE_16_10_0_PATCHES = {
    'collapse_suspension_reason',
    'record_refinanced_debts',
    'release_monthly_advances_applied_to_other_charges',
}


class PatchIdentityTests(unittest.TestCase):
    def test_registry_and_original_identities(self):
        self.assertEqual(len(PATCHES), 7)
        for name in PATCHES:
            module = importlib.import_module(name)
            self.assertTrue(callable(module.execute))
            original = 'qota.patches.' + name.rsplit('.', 1)[1].split('_', 3)[3]
            for rows, completion in (([], None), ([frappe._dict(name='log', skipped=0, traceback=None)], 'log')):
                with self.subTest(name=name, rows=rows), patch.object(frappe, 'get_all', return_value=rows), \
                    patch.object(migration_identity, 'executed', return_value=completion):
                    self.assertEqual(migration_identity.historical_completion(original), bool(rows))
            with patch.object(migration_identity.frappe, 'get_all', return_value=[frappe._dict(name='log',skipped=0,traceback='')]), \
                patch.object(migration_identity, 'executed', return_value='log'), \
                patch.object(module, '_migrate', side_effect=AssertionError('Historical body repeated')):
                module.execute()
        self.assertNotIn('x_x', '\n'.join(PATCHES))
        files={p.name for p in (ROOT/'patches').glob('*.py')}
        self.assertEqual(files, {'__init__.py',
            *[n.rsplit('.',1)[1]+'.py' for n in PATCHES]})

    def test_skipped_traceback_duplicate_and_incomplete_logs_stop(self):
        clean=frappe._dict(name='clean',skipped=0,traceback='')
        cases=[([frappe._dict(name='skip',skipped=1,traceback='failure')],'skip'),
            ([frappe._dict(name='bad',skipped=0,traceback='failure')],'bad'),
            ([clean,clean],'clean'), ([frappe._dict(name='null',skipped=None,traceback='')],None), ([clean],None)]
        for rows,executed in cases:
            with self.subTest(rows=rows),patch.object(frappe,'get_all',return_value=rows), \
                patch.object(migration_identity,'executed',return_value=executed):
                with self.assertRaisesRegex(PatchError,'HistoricalPatchLogAmbiguous'):
                    migration_identity.historical_completion('qota.patches.example')

    def test_successful_retry_recognizes_older_skipped_history(self):
        from datetime import datetime, timedelta
        first=datetime(2026,1,1)
        skipped=frappe._dict(name='skip',skipped=1,traceback='failure',creation=first)
        clean=frappe._dict(name='success',skipped=0,traceback='',creation=first+timedelta(days=1))
        with patch.object(frappe,'get_all',return_value=[skipped,clean]),patch.object(migration_identity,'executed',return_value='success'):
            self.assertTrue(migration_identity.historical_completion('qota.patches.example'))
        clean.creation=first-timedelta(days=1)
        with patch.object(frappe,'get_all',return_value=[skipped,clean]),patch.object(migration_identity,'executed',return_value='success'):
            with self.assertRaises(PatchError):migration_identity.historical_completion('qota.patches.example')

    def test_release_versions_and_historical_git_creation(self):
        import subprocess
        self.assertEqual(
            {name.split('v16_10_0_', 1)[1] for name in PATCHES if '.v16_10_0_' in name},
            RELEASE_16_10_0_PATCHES,
        )
        for name in PATCHES:
            stem=name.rsplit('.',1)[1];original=stem.split('_',3)[3]
            if original in RELEASE_16_10_0_PATCHES:
                continue
            commit=subprocess.check_output(['git','log','--diff-filter=A','--format=%H','--',f'qota/patches/{original}.py'],cwd=ROOT.parent,text=True).strip()
            version=subprocess.check_output(['git','show',commit+':qota/__init__.py'],cwd=ROOT.parent,text=True)
            self.assertIn('"'+'.'.join(stem.split('_')[0:3]).removeprefix('v')+'"',version)


if __name__ == '__main__':
    unittest.main()
