# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""Migrate entry point for Qota navigation setup."""


def after_migrate():
	"""Apply the Qota navigation setup on migrate."""
	from qota.setup import after_install

	after_install()
