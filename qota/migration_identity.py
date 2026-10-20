"""Read-only compatibility with historical Frappe patch completion identities."""

import frappe
from frappe.modules.patch_handler import PatchError, executed


def historical_completion(original):
    """Return a satisfactory framework completion, never a claim of body execution.

    Frappe 16 writes indistinguishable Patch Log rows for execute_patch and
    set_all_patches_as_completed. Both dispositions must prevent a renamed body
    from running: installation exempts historical data migrations. A single clean
    skipped=0 row is accepted using Frappe's executed() mechanism. Unresolved skipped,
    traceback-bearing, duplicate-success or malformed records require diagnosis;
    they are never promoted to successful execution and never repaired here.
    Absence alone permits the guarded historical body to evaluate its data.
    """
    rows = frappe.get_all("Patch Log", filters={"patch": original},
        fields=["name", "skipped", "traceback", "creation"], limit_page_length=0)
    if not rows:
        return False
    clean = [row for row in rows if row.skipped == 0 and not row.traceback]
    # A normal retry can leave older skipped rows followed by one clean success.
    # Multiple successes or a later/incomplete failure remain ambiguous.
    valid = len(clean) == 1
    if valid:
        success = clean[0]
        for row in rows:
            if row is success:
                continue
            valid = bool(valid and row.skipped == 1 and row.traceback and row.creation
                and success.creation and row.creation < success.creation)
    if not valid or not executed(original):
        raise PatchError(f"HistoricalPatchLogAmbiguous: {original}")
    return True
