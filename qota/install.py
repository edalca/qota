# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

"""Migrate entry point for customizations that are not DocType files.

`bench migrate` calls `after_migrate` on an existing site, including
production. The fields and the list live in `qota.setup`.
"""


def after_migrate():
	"""Apply the Qota setup and the WhatsApp desk shell."""
	from qota.whatsapp_desk import ensure_whatsapp_desk
	from qota.setup import after_install

	after_install()
	ensure_whatsapp_desk()
