# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class Subscriber(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        age: DF.Int
        birth_date: DF.Date | None
        can_read_and_write: DF.Check
        eligible_for_board: DF.Check
        email: DF.Data | None
        full_name: DF.Data
        gender: DF.Literal["Male", "Female", "Other"]
        id_expiration_date: DF.Date | None
        id_issue_date: DF.Date | None
        id_number: DF.Data
        id_type: DF.Literal["DNI", "RTN", "Passport", "Residence Card"]
        is_honduran: DF.Check
        is_resident: DF.Check
        issuing_country: DF.Link | None
        legal_representative: DF.Link | None
        primary_phone: DF.Data | None
        status: DF.Literal["Active", "Inactive", "Blocked"]
        subscriber_type: DF.Literal["Natural Person", "Juridical Person"]
        tax_address: DF.SmallText | None
    # end: auto-generated types

    def validate(self):
        self.calculate_age()
        self.validate_identity()
        self.validate_id_dates()
        self.check_board_eligibility()

    def calculate_age(self):
        if self.subscriber_type == "Natural Person" and self.birth_date:
            birth = getdate(self.birth_date)
            now = getdate(today())
            self.age = now.year - birth.year - ((now.month, now.day) < (birth.month, birth.day))
        else:
            self.age = 0

    def validate_identity(self):
        if not self.id_number:
            return

        if " " in self.id_number:
            frappe.throw(_("ID Number cannot contain spaces."))

        id_clean = self.id_number.replace("-", "")

        if self.id_type == "DNI":
            if not id_clean.isdigit() or len(id_clean) != 13:
                frappe.throw(_("DNI must be exactly 13 digits."))
            self.is_honduran = 1
            self.is_resident = 1

        elif self.id_type == "Residence Card":
            self.is_honduran = 0
            self.is_resident = 1

        elif self.id_type == "RTN":
            if not id_clean.isdigit() or len(id_clean) != 14:
                frappe.throw(_("RTN must be exactly 14 digits."))
            if self.subscriber_type == "Natural Person":
                frappe.throw(_("Natural Persons cannot use RTN as primary ID."))
            self.is_honduran = 0
            self.is_resident = 0

        else:
            self.is_honduran = 0
            self.is_resident = 0

    def validate_id_dates(self):
        if self.id_type in ["Passport", "Residence Card"]:
            if self.id_issue_date and getdate(self.id_issue_date) > getdate(today()):
                frappe.throw(_("Issue date cannot be in the future."))
            if self.id_expiration_date and getdate(self.id_expiration_date) < getdate(today()):
                frappe.throw(_("ID document has expired."))

    def check_board_eligibility(self):
        """Art. 13: Honduran, Resident, Read/Write, 18+ years old"""
        if (self.subscriber_type == "Natural Person" and
                self.is_honduran and
                self.is_resident and
                self.can_read_and_write and
                self.age >= 18):
            self.eligible_for_board = 1
        else:
            self.eligible_for_board = 0
