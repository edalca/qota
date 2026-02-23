Tienes razón, Edwin. Aquí tienes la documentación del **Doctype: Meter Reading** completamente en inglés, siguiendo la estructura que definiste y basándome en la lógica técnica de tu código.

---

### 📄 Doctype: Meter Reading

#### 1. Purpose

The **Meter Reading** DocType is designed to record water consumption for contracts under the **Metered** billing basis. Its primary function is to serve as the foundation for variable billing calculations, ensuring chronological integrity and preventing duplicate entries within the same billing period.

#### 2. Key Fields & Data Structure

Detailed configuration of the primary fields within the framework:

| Fieldname | Label | Fieldtype | Options / Details |
| --- | --- | --- | --- |
| `service_contract` | Service Contract | **Link** | `Service Contract` (Required) |
| `subscriber` | Subscriber | **Link** | `Subscriber` (Read-only; fetched from Contract) |
| `premises` | Premises | **Link** | `Premises` (Read-only; fetched from Contract) |
| `reading_date` | Reading Date | **Date** | Date of the meter reading (Required) |
| `previous_reading` | Previous Reading | **Float** | Read-only; fetched automatically from history |
| `current_reading` | Current Reading | **Float** | Measured value captured in the field (Required) |
| `consumption` | Consumption (m³) | **Float** | Read-only; calculated difference |
| `full_name` | Full Name / Company Name | **Data** | Read-only; fetched from Subscriber |

#### 3. Business Logic (Server-Side: `meter_reading.py`)

* **Automatic Previous Reading Retrieval**: The system automatically looks for the last submitted reading (`docstatus=1`) for the contract. If none is found, it uses the initial reading defined in the **Service Contract**.
* **Consumption Calculation**: It subtracts the previous reading from the current one. The system throws an error if the current reading is lower than the previous one to ensure data validity.
* **Chronological Validation**: Prevents entering readings with a date earlier than existing submitted records to maintain a consistent history.
* **Duplicate Control**: Uses the `reading_window_days` from **Billing Settings** to block multiple readings for the same contract within a specific timeframe (e.g., a 5-day window).

#### 4. UI Logic (Client-Side: `meter_reading.js`)

* **Filtered Lookups**: The contract search is restricted to only show **Active** contracts with a **Metered** billing basis.
* **Real-Time Feedback**: Upon entering the current reading, the form calculates the consumption instantly and displays a red warning if the value is inconsistent.
* **Automatic Context Loading**: When a contract is selected, the script fetches the latest reading to facilitate user entry.

#### 5. Relations

* **Service Contract**: The parent document that links the reading to a specific connection.
* **Subscriber**: Links the reading to the responsible party.
* **Premises**: Identifies the physical location where the meter is installed.

---

**¿Continuamos con el Doctype: Debt Refinancing o el de Billing Settings?** Ambos tienen lógica importante que documentar.