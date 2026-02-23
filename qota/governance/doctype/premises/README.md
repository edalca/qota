### 📄 Doctype: Premises

#### 1. Purpose

The **Premises** DocType is a root master record that identifies and manages the physical properties (lots, houses, or buildings) where services are provided. It maintains the geographic location and technical attributes of each property to ensure precise service delivery and billing context.

#### 2. Key Fields & Data Structure

| Fieldname | Label | Fieldtype | Options / Details |
| --- | --- | --- | --- |
| `status` | Status | **Select** | `Active`, `Inactive` |
| `sector` | Sector | **Data** | Neighborhood or sector name |
| `block` | Block | **Data** | Block/Manzana identification |
| `house_number` | House Number | **Data** | Specific house or lot number |
| `address_reference` | Address Reference | **Small Text** | Physical landmarks for location |
| `registration_id` | Registration ID | **Data** | Property Registry ID (Unique) |
| `nature` | Nature | **Select** | `Urban`, `Rural` |
| `area_sqm` | Area (sqm) | **Float** | Surface area in square meters |
| `meter_id` | Meter ID | **Data** | Physical meter serial number (Unique) |
| `improvement_details` | Improvement Details | **Small Text** | Notes on property upgrades |

#### 3. Business Logic (Server-Side: `premises.py`)

* **Unique Location Validation**: Prevents duplicate property records by validating the unique combination of `sector`, `block`, and `house_number`.
* **Immutable Fields Enforcement**: Protects data integrity by preventing changes to `registration_id`, `sector`, `block`, and `house_number` after the initial save.
* **Custom Search Query**: Implements `premises_search` to allow advanced filtering by concatenated address strings in link fields.

#### 4. UI Logic (Client-Side: `premises.js`)

* **Field Locking**: Automatically sets core location fields and the registration ID to read-only once the document is saved to prevent accidental modifications.
