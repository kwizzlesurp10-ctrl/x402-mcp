OFFLINE KEYS — never commit private key files.

- buyer-hot.key  → hot buyer (EVM_PRIVATE_KEY). Burner only.
- cold-receive.key → seller payTo / DEFAULT_PAY_TO. Keep offline or in host secrets.

These paths are gitignored (see .gitignore `.keys/**` with README exception only).
If a private key ever lands in git history, rotate immediately and scrub history.
