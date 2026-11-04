# US City Property-Check Response Schema

All paid `GET /us/{code}/property-check` responses (and the canonical
`GET /mn/property-check` product) share one JSON shape after settlement.
Adapters may attach legacy city-specific keys at the top level for backward
compatibility; structured copies also appear under `records`.

## Decision fields (read these first)

| Field | Type | Description |
|-------|------|-------------|
| `verdict` | string | Normalized action token: `licensed`, `not_licensed`, `expired`, `violations_open`, `flagged`, or `unknown`. |
| `summary` | string | One-sentence explanation an agent can surface to a user. |
| `compliance_verdict` | string | Legacy city-specific token (stable for existing integrations). |
| `confidence` | string | `high` / `medium` / `low` — address match quality vs returned rows. |
| `data_as_of` | string (ISO) | Freshness timestamp (`generated_at` from the join). |
| `source_url` | string \| null | Primary city open-data record or dataset URL. |
| `key_dates` | object | `{ "issued": string\|null, "expires": string\|null }` from the best registration row. |
| `open_violations_count` | int \| null | Open enforcement cases when the source exposes them. |

## Identity & query

| Field | Type |
|-------|------|
| `city` | string — URL slug (`sea`, `mn`, …) |
| `city_name` | string |
| `state` | string — USPS code |
| `address_queried` | string — buyer input |
| `address_normalized` | string \| null — uppercase, collapsed whitespace |

## Registration & violations

| Field | Type |
|-------|------|
| `registered` | bool \| null |
| `licensed` | bool \| null — MN alias / legacy |
| `registrations` | array of normalized registration objects |
| `violation_cases` | object — always includes `total`, `open`, `abated`, `recent`, `note` (null when absent) |
| `violation_cases_total` | int |
| `records` | object — `{ registrations, violation_cases, … }` copy of raw adapter fields |

Each registration object includes (null when not in source data):
`address`, `address_normalized`, `license_number`, `registration_number`,
`status`, `issue_date`, `expiration_date`, `record_url`, `parcel_number`,
`license_type`, `rental_units`, plus any city-specific passthrough keys.

## Provenance

| Field | Type |
|-------|------|
| `sources` | string[] — dataset API URLs |
| `disclaimer` | string |
| `generated_at` | string (ISO) |
| `network_product` | `"us-city-open-data-compliance"` |
| `canonical_resource` | string \| null — e.g. `/mn/property-check` for Minneapolis |

## JSON Schema

Programmatic schema: `app.city_compliance.schema.json_schema_document()`.

Free shape preview: `GET /us/{code}/property-check/sample` (fixed address, no payment).
