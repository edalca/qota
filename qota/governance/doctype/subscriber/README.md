### 📄 Doctype: Subscriber

#### 1. Purpose

The **Subscriber** DocType is the root master record for all service users within the **Qota** system. It stores legal identity, contact information, and residency status required by the **Ley Marco del Sector Agua Potable y Saneamiento** (Honduras).

#### 2. Key Fields & Data Structure

Detailed configuration of the primary fields within the framework:

| Fieldname | Label | Fieldtype | Options / Details |
| --- | --- | --- | --- |
| `subscriber_type` | Subscriber Type | **Select** | `Natural Person`, `Juridical Person` |
| `full_name` | Full Name / Company Name | **Data** | - |
| `id_type` | ID Type | **Select** | `DNI`, `RTN`, `Passport`, `Residence Card` |
| `id_number` | ID Number | **Data** | - |
| `status` | Status | **Select** | `Active`, `Inactive`, `Blocked` |
| `is_honduran` | Is Honduran | **Check** | Set automatically via JS |
| `is_resident` | Is Local Resident | **Check** | Set automatically via JS |
| `issuing_country` | Issuing Country | **Link** | `Country` |
| `id_issue_date` | Issue Date | **Date** | - |
| `id_expiration_date` | Expiration Date | **Date** | - |
| `birth_date` | Birth Date | **Date** | - |
| `age` | Age | **Int** | Read-only; calculated by server |
| `gender` | Gender | **Select** | `Male`, `Female`, `Other` |
| `can_read_and_write` | Can Read and Write | **Check** | - |
| `eligible_for_board` | Eligible for Board | **Check** | Read-only; Art. 13 compliance |
| `legal_representative` | Legal Representative | **Link** | `Subscriber` |
| `primary_phone` | Phone | **Data** | - |
| `email` | Email | **Data** | - |
| `tax_address` | Address | **Small Text** | - |

#### 3. Business Logic (Server-Side: `subscriber.py`)

* **Identity Validation**: Ensures the **DNI** is exactly 13 digits and the **RTN** is 14 digits, strictly forbidding spaces in any identification number.
* **Age Calculation**: Automatically computes the `age` from the `birth_date` on every save.
* **Art. 13 Compliance**: The system evaluates if a subscriber is eligible for a Water Board position based on being a Natural Person, Honduran, resident, literate, and at least 18 years old.
* **Identity Date Checks**: Validates that issue dates are not in the future and that documents are not expired.

#### 4. UI Logic (Client-Side: `subscriber.js`)

* **Dynamic ID Filtering**: Filters the `id_type` options based on the `subscriber_type` (e.g., restricting RTN for natural persons and DNI for juridical persons).
* **Automatic Residency Logic**: Automatically sets the `is_honduran` and `is_resident` flags when selecting identification types like DNI or Residence Card to ensure data consistency.
* **Input Sanitization**: Specifically prevents the entry of spaces within the `id_number` field during user input.
