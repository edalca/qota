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

* **Ledger Reconciliation**: Upon submission, it applies each line to the linked Debt Ledger Entry and reduces that debt's outstanding amount. A Monthly Fee line without a debt yet stays as an advance until the monthly bill is created. The receipt header `unallocated_amount` is recalculated when an advance is later applied.
* **Reconnection**: Paying a receipt does not restore the service. Reconnection is a separate order. It can be executed only after its fee is paid, or immediately when the fee is zero.
* **Lump Sum vs. Itemized**: Supports both global payments (Lump Sum) and detailed month-by-month selections via the child table.

#### 4. UI Logic (Client-Side: `payment_receipt.js`)

* **Smart Tools**: Includes a "Load Pending Debt" button to automatically pull unpaid bills into the payment table.
* **Future Payments**: Provides a "Pay Multiple Months" tool to calculate and add rows for future months based on estimated rates.
* **Visual Status**: Features a "View Account Status" dialog that shows a color-coded table (Red for debt, Green for paid, Blue for advance) for the current year.

#### 5. Relations

* **Service Contract**: Identifies the account being paid.
* **Payment Receipt Item**: Child table used to allocate funds to specific billing periods or concepts.
