# US City Open-Data Compliance Network

Multi-city paid x402 product under `/us/{code}/property-check`.

## Cities (v1–v2)

| Code | City | State | Open data focus |
|------|------|-------|-----------------|
| `mn` | Minneapolis | MN | Rental licenses + violations + condemned (delegates to `app.mn_compliance`) |
| `sea` | Seattle | WA | RRIO rental registration (Socrata) |
| `nyc` | New York City | NY | HPD multi-dwelling registration + HMC violations |
| `chi` | Chicago | IL | Building code violations (no citywide rental license feed) |
| `den` | Denver | CO | Short-term rental licenses |
| `sf` | San Francisco | CA | DBI notices of violation |
| `lax` | Los Angeles | CA | Open Building & Safety code enforcement cases |
| `bos` | Boston | MA | Building and property violations (CKAN) |
| `phi` | Philadelphia | PA | L&I property maintenance violations (Carto) |
| `orl` | Orlando | FL | Short-term rental licenses |
| `nola` | New Orleans | LA | Active short-term rental licenses |
| `moco` | Montgomery County | MD | Housing licensing + active code violations |
| `gain` | Gainesville | FL | Code complaints / violations / permits |
| `kc` | Kansas City | MO | Open exterior building violations |

### Search notes (2026-08-06)

Public Socrata catalog sweep across 80+ domains found **88** rental/violation-related resources.
Skipped for now (no address column, 403, or non-queryable): Cambridge STR (lat/long only),
Oakland rental list (403 non-tabular), Cincinnati code (coords only), many ArcGIS-only portals.

## Endpoints

| Method | Path | Price |
|--------|------|-------|
| GET | `/us/cities` | free catalog |
| GET | `/us/{code}/property-check/sample` | free fixed-address sample |
| GET | `/us/{code}/property-check?address=` | `$0.01` USDC on Base (`city_network_price`) |

Minneapolis **canonical** path remains `/mn/property-check` (unchanged).  
Network path `/us/mn/property-check` is a uniform-envelope alias for catalog agents.

## Wire protocol

Same as MN: unpaid → HTTP 402 + `PAYMENT-REQUIRED` **before** address validation;
paid path validates address then verify+settle; `PAYMENT-RESPONSE` on success.

## MCP golden path (A2A packaging)

The network is **HTTP-first** and also exposed as three thin MCP tools on the
same host (`/.well-known/mcp`). Tools wrap the existing URLs — they are not a
second product.

| Step | MCP tool | HTTP equivalent | Payment |
|------|----------|-----------------|---------|
| 1 | `list_us_cities` | `GET /us/cities` | free |
| 2 | `get_us_city_property_sample(city_code)` | `GET /us/{code}/property-check/sample` | free |
| 3 | `check_us_city_property(city_code, address)` | `GET /us/{code}/property-check?address=` | `$0.01` USDC |

Paid step requires `EVM_PRIVATE_KEY` on the **MCP client host** (buyer wallet).
Seller-only Render deploys omit that key; agents still get a 402 probe +
`how_to_pay` handoff from `check_us_city_property`, or call `pay_and_fetch` from
a wallet-enabled client against `paid_url`.

```text
list_us_cities
  → pick code (e.g. mn)
get_us_city_property_sample(city_code="mn")
  → validate JSON shape
check_us_city_property(city_code="mn", address="1700 Penn Ave N")
  → settle + report  (or pay_and_fetch url=<paid_url>?address=…)
```

A2A Agent Card skills under `/.well-known/agent.json` (see `app/agent_surface.py`)
advertise the same HTTP interfaces; MCP tool names are the Cursor/stdio entry.

## Config

- `CITY_NETWORK_PRICE` / `city_network_price` (default `$0.01`)
- Existing `MN_*` settings still drive the ArcGIS join for both `/mn/*` and `/us/mn/*`

## Adding a city

1. `app/city_compliance/cities/{code}.py` with `SPEC`, `check_property`, `discovery_output_example`
2. Register module in `app/city_compliance/registry.py` `_MODULES`
3. Extend tests in `tests/test_city_compliance.py`
4. Live-probe sample address before deploy
