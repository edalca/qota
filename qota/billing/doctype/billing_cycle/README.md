### 📄 Doctype: Billing Cycle

#### 1. Purpose

The **Billing Cycle** DocType is the mass-billing engine of the **Qota** system. It automates the periodic generation of invoices for all active service contracts (Flat Rate, Metered, or both). It ensures chronological continuity, prevents duplicate charges, and provides a pre-execution diagnostic tool to identify billing gaps.

#### 2. Key Fields & Data Structure

| Fieldname | Label | Fieldtype | Options / Details |
| --- | --- | --- | --- |
| `fiscal_year` | Billing Year | **Link** | `Billing Year` (Filtered by open years) |
| `fiscal_month` | Fiscal Month | **Select** | January through December |
| `billing_basis` | Billing Basis | **Select** | `Flat Rate`, `Metered`, `All` |
| `posting_date` | Posting Date | **Date** | Billing date (Default: Today) |
| `edit_posting_date` | Edit Posting Date | **Check** | Unlocks the `posting_date` field |
| `status` | Status | **Select** | `Draft`, `Queue`, `Completed`, `Cancelled` |
| `start_date` | Start Date | **Date** | Start of service coverage |
| `end_date` | End Date | **Date** | End of service coverage |
| `total_generated` | Total Generated | **Currency** | Sum of all successfully created bills |
| `total_contracts` | Total Processed | **Int** | Count of bills successfully created |
| `issues` | Billing Issues | **Table** | `Billing Cycle Issue` (Logs execution errors) |

#### 3. Business Logic (Server-Side: `billing_cycle.py`)

* **Sequence & Gap Validation**: Ensures no gaps exist between billing cycles by comparing the current `start_date` with the `end_date` of the last submitted cycle.
* **Background Queue Management**: Uses `frappe.enqueue` to run the billing engine in a background worker, preventing browser timeouts during large batch runs (e.g., 750+ contracts).
* **Reset Mechanism**: Provides a whitelisted `reset_status` method that allows administrators to manually return a "stuck" cycle from `Queue` back to `Draft`.
* **Issue Persistence**: Unlike previous versions, the `run_billing_engine` now populates the `issues` child table with specific error reasons (e.g., "Missing Reading", "Already Billed", "Future Start Date"), providing a permanent audit trail of skipped contracts.
* **Automatic Rollback**: If a submitted cycle is cancelled, the system automatically iterates through and cancels all linked `Monthly Bill` documents.
* **Critical Error Recovery**: The background worker includes a `try-except` block that resets the cycle to `Draft` and logs the traceback if the entire process fails.

#### 4. UI Logic (Client-Side: `billing_cycle.js`)

* **Interactive Diagnostics**: Features a "Get Diagnostics" button in `Draft` mode that triggers a dry run and reloads the document to display issues in the `issues` table.
* **Emergency Reset Tool**: Adds a "Reset to Draft" button under the "Actions" menu when the status is `Queue`, enabling manual recovery if workers fail.
* **Real-time Refresh**: Listens for the `billing_cycle_finished` socket event to automatically refresh the UI and notify the user once the background processing is complete.
* **Automated Date Calculation**: Dynamically updates `start_date` and `end_date` based on the selected month/year and the `cycle_start_day` configured in **Billing Settings**.
* **Navigation Links**: Displays a "View Generated Bills" button after completion to navigate directly to the filtered list of `Monthly Bills`.

#### 5. Relations

* **Billing Year**: Defines the fiscal period for the run.
* **Billing Cycle Issue**: Child table used to store logs for skipped or failed contract billing.
* **Monthly Bill**: The resulting invoice documents created during execution.
* **Service Contract**: The primary data source for the billing engine.