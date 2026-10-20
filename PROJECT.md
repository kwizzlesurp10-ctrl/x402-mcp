# Project: Smithery.ai 100/100 Quality Score & Agent ID Cards

## Architecture
`x402-mcp` is a dual-transport Model Context Protocol (MCP) server providing autonomous crypto commerce and data tools for AI agents.
- **Transports**: FastMCP stdio transport (`run_stdio.py`) and FastAPI Streamable HTTP transport (`app/main.py` -> `app/mcp_server.py`).
- **Core Modules**:
  - `app/mcp_server.py`: FastMCP instance (`mcp`), tool definitions, docstrings, annotations, prompts, and resources.
  - `app/tools_registry.py`: Canonical registry (`TOOL_SPECS`, `EXPECTED_TOOL_NAMES`, `TOOL_COUNT`).
  - `app/agent_surface.py`: Agent-to-Agent discovery (`agent_card`, `agents_json`, `server_card`).
  - `app/manifest.py`: MCP manifest endpoints.
  - `smithery.yaml`: Smithery registry specification (`configSchema`, `startCommand`, `commandFunction`, metadata).
  - `package.json`: NPM package metadata and discovery.
  - `README.md`: User/agent documentation, quickstart, tool parameter tables, sample prompts.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Tool Agent ID Cards | Attach Agent ID card schemas and metadata to all MCP tools | M1 | ORIGINAL_REQUEST R1 |
| 2 | Tool Parameter Docstrings | Add comprehensive `Args:` docstrings to all tool functions so FastMCP generates rich parameter JSON schemas | M1 | Smithery Checklist |
| 3 | FastMCP Tool Annotations | Add `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` annotations to all tools | M1 | Smithery Checklist |
| 4 | Agent Card Tool & Resource | Expose `get_agent_card` MCP tool and `x402://agent-card` resource for direct MCP agent discovery | M1 | ORIGINAL_REQUEST R1 |
| 5 | FastMCP Prompts & Resources | Register standard MCP prompts and resources in `app/mcp_server.py` | M1 | Smithery Checklist |
| 6 | Smithery Configuration V2 | Modernize `smithery.yaml` with top-level `configSchema`, `commandFunction`, and rich metadata | M2 | Smithery Checklist |
| 7 | Package Metadata Enrichment | Update `package.json` with description, version, keywords, author, license, repo, homepage, scripts | M2 | Smithery Checklist |
| 8 | Server JSON Sync | Synchronize `server.json` schema and metadata with `smithery.yaml` and `package.json` | M2 | Smithery Checklist |
| 9 | README Smithery Badge & Quickstart | Add official Smithery badge, `npx -y @smithery/cli install` quickstart, and client config snippets | M3 | Smithery Checklist |
| 10 | README Parameter Tables & Prompts | Document all tools with full parameter tables, types, and sample LLM prompts | M3 | Smithery Checklist |
| 11 | Test Suite Synchronization | Update and verify all 604+ tests across `tests/` for new tools, docstrings, readme, and configs | M3 | Verification |
| 12 | Agent-as-Judge 100/100 Evaluation | Independent verification against the full 10-dimension Smithery.ai quality rubric | M4 | ORIGINAL_REQUEST Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | MCP Tools, Agent ID Cards & Prompts/Resources | `app/mcp_server.py`, `app/tools_registry.py`, `app/agent_surface.py`, `app/manifest.py` | none | DONE |
| M2 | Smithery Config & Package Metadata | `smithery.yaml`, `package.json`, `server.json` | M1 | DONE |
| M3 | Documentation & Test Synchronization | `README.md`, `tests/*` | M1, M2 | DONE |
| M4 | Final 100/100 Agent-as-Judge & Verification | Full repository evaluation against Smithery checklist | M1, M2, M3 | DONE |

## Interface Contracts
### M1: `app/tools_registry.py` ↔ `app/mcp_server.py` ↔ `app/manifest.py`
- `TOOL_SPECS` in `app/tools_registry.py` defines canonical tool metadata, descriptions, schemas, and Agent ID cards.
- `app/mcp_server.py` registers all tools with FastMCP using exact matching names, `Args:` docstrings, and `annotations={...}`.
- New tool `get_agent_card` returns structured Agent Card JSON data.
- MCP prompts: `onboarding_flow`, `x402_tool_selector`, `generate_quote`, `troubleshoot_payment`.
- MCP resources: `x402://agent-card`, `x402://server-card`, `x402://tools-manifest`, `x402://pricing-table`.

### M2: `smithery.yaml` ↔ `package.json`
- `smithery.yaml` conforms to Smithery JSON schema with `configSchema` defining required and optional environment settings (`X402_PAY_TO_ADDRESS`, `EVM_PRIVATE_KEY`, `X402_FACILITATOR_URL`, etc.).
- `commandFunction` generates the startup command and arguments.
- `package.json` provides unified package metadata (version, description, keywords, license, repository).

### M3: `README.md` ↔ Test Suite
- `README.md` reflects the accurate tool inventory, parameter schemas, installation guides, and Smithery badge.
- `tests/test_readme.py`, `tests/test_manifest.py`, `tests/test_mcp_tools.py`, `tests/test_server_json.py` pass without errors.

## Code Layout
- `app/`: Python backend source files (FastAPI, FastMCP, business logic, commerce, tools).
- `tests/`: Hermetic pytest test suite.
- `smithery.yaml`: Smithery.ai server configuration.
- `package.json`: NPM package metadata.
- `server.json`: MCP standard server manifest.
- `README.md`: Documentation.
- `.agents/`: Agent metadata and reports only.
