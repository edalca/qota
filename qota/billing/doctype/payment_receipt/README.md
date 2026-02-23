### 📄 Doctype: Payment Receipt

#### 1. Purpose

The **Payment Receipt** is the primary collection document. It records payments made by subscribers to settle outstanding debts or advance future monthly fees. It handles complex scenarios like automatic service reconnection and debt ledger reconciliation.

#### 2. Key Fields & Data Structure

| Fieldname | Label | Fieldtype | Options / Details |
| --- | --- | --- | --- |
| `service_contract` | Service Contract | **Link** | `Service Contract` (Required) |
| `amount_paid` | Amount Paid | **Currency** | Total money received |
| `payment_date` | Payment Date | **Date** | Default: Today |
| `mode_of_payment` | Mode of Payment | **Select** | Cash, Bank Transfer, Check, Credit Card |
| `is_reconnection_payment` | Is Reconnection? | **Check** | Triggers automatic status change |
| `payment_items` | Items | **Table** | `Payment Receipt Item` (Monthly breakdown) |
| `current_debt` | Current Debt | **Currency** | Read-only; live balance from Ledger |
| `total_to_pay` | Total Pending | **Currency** | Read-only; includes fees and arrears |

#### 3. Business Logic (Server-Side: `payment_receipt.py`)

* **Ledger Reconciliation**: Upon submission, it creates negative `Debt Ledger Entries` (Credits) to reduce the subscriber's balance. If specific months are paid, it records the `fiscal_month` and `fiscal_year` for accurate aging reports.
* **Automatic Reconnection**: If the contract is "Suspended" and the payment covers the `reconnection_charge`, the system automatically reverts the contract status to "Active".
* **Lump Sum vs. Itemized**: Supports both global payments (Lump Sum) and detailed month-by-month selections via the child table.

#### 4. UI Logic (Client-Side: `payment_receipt.js`)

* **Smart Tools**: Includes a "Load Pending Debt" button to automatically pull unpaid bills into the payment table.
* **Future Payments**: Provides a "Pay Multiple Months" tool to calculate and add rows for future months based on estimated rates.
* **Visual Status**: Features a "View Account Status" dialog that shows a color-coded table (Red for debt, Green for paid, Blue for advance) for the current year.

#### 5. Relations

* **Service Contract**: Identifies the account being paid.
* **Payment Receipt Item**: Child table used to allocate funds to specific billing periods or concepts.
