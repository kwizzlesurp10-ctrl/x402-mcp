# Original User Request

## 2026-08-21T11:58:34Z

<USER_REQUEST>
Implement and activate the "Fusion Panda Cyberpunk Poster Prompt Pack" product (`merchforge-fusion-panda-poster-kit-v1`) as a paid x402 tool in the `x402-mcp` codebase. Connect the poster generator tool to a real image generator API (e.g. OpenAI DALL-E 3 or Replicate) using API keys.

Working directory: /home/keef/x402-mcp
Integrity mode: benchmark

## Requirements

### R1. MCP Tool Registration
Register the new MCP tool `generate_fusion_panda_poster` in the `x402-mcp` registry.
- Add it to `app/tools_registry.py`.
- Implement the tool wrapper in `app/mcp_server.py` using `@mcp.tool()`.
- Update `README.md`, `tests/test_readme.py`, and `tests/test_assessor.py` to match the new tool count and details.

### R2. Poster Generator Core Implementation
Implement the core logic for `generate_fusion_panda_poster` to connect to a real image generation API (OpenAI DALL-E 3 or Replicate) and generate a cyberpunk-style Fusion Panda poster.
- Handle parameters (such as `style`, `colorway`, `pose`) and inject them into the base prompts as specified in the product prompt pack.
- Support reading API keys (`OPENAI_API_KEY` or `REPLICATE_API_TOKEN`) from the environment configuration in `app/config.py`.

### R3. Paid x402 Endpoint Integration
Integrate the poster generation as a paid endpoint priced at $0.49 (`price_usd` / `price_usdc` = 0.49) on the Base network (`eip155:8453`), following the repo's existing x402 challenge-response payment/settlement flow.

## Acceptance Criteria

### Tool and Code Integrity
- [ ] Pytest suite passes successfully (`make test` runs without regressions).
- [ ] Tool registry assertions in `tests/test_readme.py` and `tests/test_assessor.py` are updated and pass.

### Execution & Verification
- [ ] A test script or mock execution verifying `generate_fusion_panda_poster` completes successfully and handles API response formatting.
- [ ] The generated response format matches the expected tool output schema containing the image URL and commerce metadata.
</USER_REQUEST>
