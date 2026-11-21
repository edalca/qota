"""Water Issue Report integrity, acknowledgment, and Subscribers navigation."""

from contextlib import ExitStack
from datetime import datetime
import unittest
import uuid
from unittest.mock import patch

import frappe
from frappe.utils import get_datetime
from qota import setup
from qota.governance.doctype.water_issue_report.water_issue_report import WaterIssueReport


INITIAL_STATE = "A water report must start as Pending without an acknowledgment."
REFERENCES = "Conversation session, conversation turn, process execution, and bot flow are required."
TEXT = "A textual description and a localizable location are required."
NAME_LINK = "The water report name must match its process execution."
IMMUTABLE = "Water report content and references are immutable."
SEEN_ONLY = "A water report can only be marked as Seen."


class WaterIssueReportTests(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(frappe.db, "commit", lambda *args, **kwargs: None))
        self.addCleanup(self.stack.close)
        self.addCleanup(self._restore)
        self.prefix = "WIR-TEST-" + uuid.uuid4().hex[:10]
        self.stamp = datetime(2026, 11, 20, 15, 4, 5)
        self._english()

    def _restore(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _english(self):
        frappe.local.lang = "en"

    def _payload(self, **overrides):
        values = dict(
            doctype="Water Issue Report",
            status="Pending",
            description="Leak beside the test meter",
            location="Synthetic north lane",
            contracts_json='["SC-TEST"]',
            conversation_session=self.prefix + "-session",
            conversation_turn=self.prefix + "-turn",
            process_execution=self.prefix,
            bot_flow=self.prefix + "-flow",
        )
        values.update(overrides)
        return values

    def _new(self, **overrides):
        """Build the QOTA controller directly. get_doc returns the extended class."""
        return WaterIssueReport(self._payload(**overrides))

    def _insert(self, **overrides):
        doc = self._new(**overrides)
        doc.insert(ignore_permissions=True)
        return doc

    def _extended_new(self, **overrides):
        return frappe.get_doc(self._payload(**overrides))

    def _message(self, exception):
        return str(exception)

    def _assert_message(self, exc_type, text, call):
        with self.assertRaises(exc_type) as caught:
            call()
        self.assertIn(text, self._message(caught.exception))
        return caught.exception

    def _user(self, roles):
        email = self.prefix.lower() + "-" + uuid.uuid4().hex[:6] + "@example.com"
        doc = frappe.get_doc(dict(
            doctype="User",
            email=email,
            first_name="Water Report",
            user_type="System User",
            send_welcome_email=0,
            roles=[dict(doctype="Has Role", role=role) for role in roles],
        ))
        doc.flags.no_welcome_email = True
        doc.insert(ignore_permissions=True)
        return doc.name

    def test_permissions_leave_manual_create_disabled(self):
        permission = next(
            row for row in frappe.get_meta("Water Issue Report").permissions
            if row.role == "System Manager"
        )
        self.assertEqual(int(permission.create or 0), 0)
        self.assertEqual(int(permission.read or 0), 1)
        self.assertEqual(int(permission.write or 0), 1)
        self.assertEqual(int(permission.delete or 0), 0)
        self.assertEqual(frappe.get_meta("Water Issue Report").allow_rename, 0)

    def test_technical_insert_and_direct_db_insert(self):
        created = self._insert()
        self.assertEqual(created.name, created.process_execution)
        self.assertEqual(created.status, "Pending")
        self.assertFalse(created.seen_by)
        self.assertFalse(created.seen_at)
        self.assertEqual(created.contracts_json, '["SC-TEST"]')

        direct = self._new(process_execution=self.prefix + "-direct")
        direct.flags.ignore_permissions = True
        direct.flags.ignore_validate = True
        direct.flags.ignore_mandatory = True
        direct.db_insert()
        stored = frappe.get_doc("Water Issue Report", self.prefix + "-direct")
        self.assertEqual(stored.name, stored.process_execution)
        self.assertEqual(stored.status, "Pending")
        self.assertFalse(stored.seen_by)
        self.assertFalse(stored.seen_at)

        bounded = "P" * 140
        accepted = self._insert(process_execution=bounded, conversation_session=bounded)
        self.assertEqual(accepted.name, bounded)
        self.assertEqual(len(accepted.process_execution), 140)

        # Administrator passes Frappe's permission bypass. Integrity still applies.
        administrator = self._new(process_execution=self.prefix + "-administrator")
        administrator.insert()
        self.assertEqual(administrator.status, "Pending")
        self._assert_message(
            frappe.ValidationError,
            REFERENCES,
            lambda: self._new(process_execution=self.prefix + "-administrator-gap", bot_flow="").insert(),
        )

    def test_incomplete_initial_state_and_length_are_rejected(self):
        cases = {
            "session": dict(conversation_session=""),
            "turn": dict(conversation_turn=None),
            "execution": dict(process_execution=""),
            "flow": dict(bot_flow=""),
        }
        for field, overrides in cases.items():
            with self.subTest(field=field):
                doc = self._new(**overrides)
                doc.flags.ignore_permissions = True
                doc.flags.ignore_mandatory = True
                doc.flags.ignore_validate = True
                self._assert_message(frappe.ValidationError, REFERENCES, doc.db_insert)
                if doc.process_execution:
                    self.assertFalse(
                        frappe.db.exists("Water Issue Report", {"process_execution": doc.process_execution})
                    )

        short = self._new(description="Leak")
        short.flags.ignore_permissions = True
        self._assert_message(frappe.ValidationError, TEXT, short.insert)
        self._assert_message(
            frappe.ValidationError,
            TEXT,
            lambda: self._new(location=" \n\t ").insert(ignore_permissions=True),
        )
        self._assert_message(
            frappe.ValidationError,
            INITIAL_STATE,
            lambda: self._new(status="Seen").insert(ignore_permissions=True),
        )
        self._assert_message(
            frappe.ValidationError,
            INITIAL_STATE,
            lambda: self._new(seen_by="Administrator").insert(ignore_permissions=True),
        )
        self._assert_message(
            frappe.ValidationError,
            INITIAL_STATE,
            lambda: self._new(seen_at=self.stamp).insert(ignore_permissions=True),
        )
        self._assert_message(
            frappe.ValidationError,
            NAME_LINK,
            lambda: self._new().insert(ignore_permissions=True, set_name=self.prefix + "-other"),
        )
        oversized = self._new(process_execution="L" * 141)
        oversized.flags.ignore_permissions = True
        oversized.flags.ignore_mandatory = True
        self._assert_message(frappe.CharacterLengthExceededError, "140", oversized.db_insert)
        self.assertFalse(frappe.db.exists("Water Issue Report", oversized.process_execution))

    def test_content_stays_immutable_and_seen_records_the_server_actor(self):
        created = self._insert()
        created = frappe.get_doc("Water Issue Report", created.name)
        with patch(
            "qota.governance.doctype.water_issue_report.water_issue_report.now_datetime",
            return_value=self.stamp,
        ):
            created.status = "Seen"
            created.seen_by = "Guest"
            created.seen_at = datetime(2000, 1, 1)
            created.save()
        self.assertEqual(created.seen_by, "Administrator")
        self.assertEqual(get_datetime(created.seen_at), self.stamp)
        stored = frappe.get_doc("Water Issue Report", created.name)
        self.assertEqual(stored.seen_by, "Administrator")
        self.assertEqual(get_datetime(stored.seen_at), self.stamp)

        changed = frappe.get_doc("Water Issue Report", created.name)
        changed.description = "A different leak description"
        self._assert_message(frappe.ValidationError, IMMUTABLE, changed.save)
        self.assertEqual(
            frappe.db.get_value("Water Issue Report", created.name, "description"),
            "Leak beside the test meter",
        )
        renamed = frappe.get_doc("Water Issue Report", created.name)
        renamed.name = self.prefix + "-renamed"
        self._assert_message(frappe.ValidationError, IMMUTABLE, renamed.validate)
        self._assert_message(frappe.ValidationError, IMMUTABLE, renamed.before_rename)

    def test_reverse_and_repeated_acknowledgment_do_not_replace_the_first(self):
        created = frappe.get_doc("Water Issue Report", self._insert().name)
        with patch(
            "qota.governance.doctype.water_issue_report.water_issue_report.now_datetime",
            return_value=self.stamp,
        ):
            created.status = "Seen"
            created.save()
        created.reload()
        created.status = "Pending"
        created.seen_by = None
        created.seen_at = None
        self._assert_message(frappe.ValidationError, SEEN_ONLY, created.save)
        self.assertEqual(frappe.db.get_value("Water Issue Report", created.name, "status"), "Seen")

        repeated = frappe.get_doc("Water Issue Report", created.name)
        repeated.seen_by = "Guest"
        repeated.seen_at = datetime(1999, 1, 1)
        repeated.status = "Seen"
        repeated.save()
        repeated.reload()
        self.assertEqual(repeated.seen_by, "Administrator")
        self.assertEqual(get_datetime(repeated.seen_at), self.stamp)

    def test_desk_create_is_rejected_and_technical_create_remains_available(self):
        manager = self._user(["System Manager"])
        frappe.set_user(manager)
        self._english()
        denied = self._new(process_execution=self.prefix + "-desk")
        with self.assertRaises(frappe.PermissionError):
            denied.insert()
        self.assertFalse(frappe.db.exists("Water Issue Report", self.prefix + "-desk"))
        denied.flags.ignore_permissions = True
        denied.insert()
        self.assertEqual(denied.status, "Pending")

        frappe.set_user("Administrator")
        self._english()
        extended = self._extended_new(process_execution=self.prefix + "-extended")
        if type(extended).validate is WaterIssueReport.validate:
            self.fail("The reference site loads Water Issue Report through an extended class.")
        with self.assertRaises(frappe.PermissionError) as caught:
            extended.insert(ignore_permissions=True)
        self.assertIn("authorized automatic Process context", str(caught.exception))
        self.assertFalse(frappe.db.exists("Water Issue Report", self.prefix + "-extended"))
        extended.flags.ignore_validate = True
        extended.flags.ignore_mandatory = True
        with self.assertRaises(frappe.PermissionError):
            extended.db_insert()
        self.assertFalse(frappe.db.exists("Water Issue Report", self.prefix + "-extended"))

        blocked = self._insert(process_execution=self.prefix + "-admin")
        loaded = frappe.get_doc("Water Issue Report", blocked.name)
        frappe.set_user("Guest")
        self._english()
        loaded.status = "Seen"
        loaded.flags.ignore_permissions = True
        self._assert_message(frappe.PermissionError, "Authentication required.", loaded.validate)
        self.assertEqual(frappe.db.get_value("Water Issue Report", blocked.name, "status"), "Pending")

        frappe.set_user("Administrator")
        self._english()
        plain = self._user([])
        report = frappe.get_doc("Water Issue Report", blocked.name)
        frappe.set_user(plain)
        self._english()
        report.flags.ignore_permissions = True
        report.status = "Seen"
        with self.assertRaises(frappe.PermissionError):
            report.validate()
        self.assertEqual(frappe.db.get_value("Water Issue Report", blocked.name, "status"), "Pending")

    def test_navigation_places_the_link_inside_operations_once(self):
        self._set_root_link()
        before = self._other_items()
        setup.ensure_navigation()
        sidebar = frappe.get_doc("Sidebar", "Subscribers")
        links = [row for row in sidebar.items if row.link_to == "Water Issue Report"]
        self.assertEqual(len(links), 1)
        self.assertTrue(setup._water_issue_link_matches(links[0]))
        labels = [row.label for row in sidebar.items]
        self.assertLess(labels.index("Operations"), labels.index("Water Issue Report"))
        self.assertLess(labels.index("Service Reconnection"), labels.index("Water Issue Report"))
        self.assertLess(labels.index("Water Issue Report"), labels.index("Reports"))
        self.assertEqual(self._other_items(), before)

        self._settle_dock_title()
        with patch.object(setup, "_save_navigation") as save:
            setup.ensure_navigation()
        self.assertFalse(save.called)

        for row in list(sidebar.items):
            if row.link_to == "Water Issue Report":
                sidebar.remove(row)
        setup._save_navigation(sidebar)
        setup.ensure_navigation()
        sidebar = frappe.get_doc("Sidebar", "Subscribers")
        links = [row for row in sidebar.items if row.link_to == "Water Issue Report"]
        self.assertEqual(len(links), 1)
        self.assertTrue(setup._water_issue_link_matches(links[0]))
        labels = [row.label for row in sidebar.items]
        self.assertLess(labels.index("Water Issue Report"), labels.index("Reports"))

        sidebar.append("items", dict(setup.WATER_ISSUE_REPORT_LINK))
        setup._save_navigation(sidebar)
        setup.ensure_navigation()
        sidebar = frappe.get_doc("Sidebar", "Subscribers")
        self.assertEqual(sum(row.link_to == "Water Issue Report" for row in sidebar.items), 1)

        for row in list(sidebar.items):
            if row.label == "Operations" or row.link_to == "Water Issue Report":
                sidebar.remove(row)
        setup._save_navigation(sidebar)
        setup.ensure_navigation()
        sidebar = frappe.get_doc("Sidebar", "Subscribers")
        self.assertFalse(any(row.label == "Operations" for row in sidebar.items))
        self.assertFalse(any(row.link_to == "Water Issue Report" for row in sidebar.items))

    def _set_root_link(self):
        sidebar = frappe.get_doc("Sidebar", "Subscribers")
        for row in list(sidebar.items):
            if row.link_to == "Water Issue Report":
                sidebar.remove(row)
        sidebar.append("items", dict(
            type="Link",
            label="Water Issue Report",
            link_type="DocType",
            link_to="Water Issue Report",
            child=0,
            indent=0,
            icon="clipboard",
            open_in_new_tab=1,
        ))
        setup._save_navigation(sidebar)

    def _other_items(self):
        sidebar = frappe.get_doc("Sidebar", "Subscribers")
        return [
            (row.type, row.label, row.link_to, int(row.child or 0))
            for row in sidebar.items
            if row.link_to != "Water Issue Report"
        ]

    def _settle_dock_title(self):
        dock = frappe.get_doc("Dock", "qota")
        for row in dock.items:
            if row.link_type == "Sidebar" and row.link_to == "Subscribers":
                row.title = "Governance"
        setup._save_navigation(dock)
