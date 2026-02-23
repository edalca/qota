### 📄 Doctype: Monthly Bill

#### 1. Purpose

The **Monthly Bill** DocType is the official invoice issued to a subscriber for water services. It consolidates all charges for a specific fiscal month and year, including the base rate, consumption-based fees (for metered connections), and any additional fees. It serves as a primary financial record and updates the subscriber's balance in the **Debt Ledger**.

#### 2. Key Fields & Data Structure

| Fieldname | Label | Fieldtype | Options / Details |
| --- | --- | --- | --- |
| `service_contract` | Service Contract | **Link** | `Service Contract` (Required) |
| `full_name` | Subscriber Name | **Data** | Read-only; fetched from Contract |
| `premises` | Premises | **Link** | Read-only; fetched from Contract |
| `posting_date` | Posting Date | **Date** | Billing date |
| `status` | Status | **Select** | `Draft`, `Submitted`, `Cancelled`, `Paid` |
| `fiscal_year` | Billing Year | **Link** | `Billing Year` (Filtered by active years) |
| `fiscal_month` | Fiscal Month | **Select** | January through December |
| `billing_cycle` | Billing Cycle | **Link** | `Billing Cycle` (Batch reference) |
| `start_date` | Start Date | **Date** | Start of the service period |
| `end_date` | End Date | **Date** | End of the service period |
| `items` | Breakdown | **Table** | `Monthly Bill Item` |
| `grand_total` | Total to Pay | **Currency** | Final calculated amount |

#### 3. Business Logic (Server-Side: `monthly_bill.py`)

* **Submittable Document**: The DocType is submittable, meaning it locks financial data once verified.
* **Fiscal Period Control**: Linked to a specific `Billing Year` and `Fiscal Month` to ensure accurate historical reporting and debt aging.
* **Batch Integration**: Each bill is typically associated with a `Billing Cycle`, allowing the system to track mass-billing operations.
* **Automatic Naming**: Uses a specific expression for naming: `MBILL-.YY.-.MM.-.####`, which includes the year and month of creation.

#### 4. UI Logic (Client-Side: `monthly_bill.js`)

* **Data Fetching**: Automatically pulls the `full_name` and `premises` from the selected `Service Contract` to reduce data entry errors.
* **Posting Date Control**: Includes an `edit_posting_date` check to allow or restrict manual changes to the billing date based on system permissions.
* **Read-only Sections**: The breakdown table and totals are marked as read-only to ensure they only reflect calculated values from the billing process.

#### 5. Relations

* **Service Contract**: The source of billing rules, rates, and property information.
* **Billing Cycle**: The process responsible for generating the bill in a mass run.
* **Monthly Bill Item**: Child table that stores the individual lines of the invoice (e.g., Fixed Charge, Consumption, Surcharges).
* **Billing Year**: Used for grouping and validating the fiscal period.
