# A2A task capability (ownership)

Tasks created by `POST /a2a` (`message/send`) are bound to an unguessable **capability token** returned once as `capabilityToken` on the task object.

## Client requirements

- **Store** `capabilityToken` when you receive a task (payment-required, free completed, or other states).
- For **`tasks/get`** and **`tasks/cancel`**, prove ownership using **one** of:
  - Header: `X-A2A-Task-Capability: <token>` (alias: `A2A-Task-Capability`), or
  - JSON-RPC params: `"capabilityToken": "<token>"`
- For **`message/send`** when continuing a paid task (`payment-submitted` / `x402.payment.payload`), include the same token in `message.metadata`:
  - `x402.task.capability` (preferred), or `taskCapability`

## Optional client binding

- Header `X-A2A-Client-Id` (alias `A2A-Client-Id`): when set on **creation**, subsequent task operations with a **different** client id are rejected. Omit on all calls if you do not use client binding.

## Migration

Older clients that only passed `taskId` will receive JSON-RPC error **-32003** `forbidden` until they send the capability token as above.

## Rollback

With `REDIS_URL` + durable tasks: rolling back software does not erase `a2a:task:*` keys until TTL; clients must still present the same capability.

**Scoped rollback (A2A tasks only):** set `A2A_TASK_STORE_REDIS=false` and redeploy. Tasks revert to **per-process memory** (lost on restart; not shared across workers). **Do not** unset `REDIS_URL` just to disable A2A durability — that also drops Redis-backed **MCP commerce coordination**, quota, and other shared state. To stop persisting A2A payloads while keeping MCP coordination, keep `REDIS_URL` and turn off `A2A_TASK_STORE_REDIS` only.

## Durability (when `REDIS_URL` is set and reachable)

- Tasks are stored under `a2a:task:{task_id}` with JSON payload (`_a2a_store_v: 1`), TTL `A2A_TASK_TTL_SECONDS` (default 7 days).
- **`SkillBinding` objects are not serialized** — after load we reattach the skill by `skillId` from the current server registry. If a skill is removed, the task fails with a clear error.
- **Capability secrets:** Redis stores `capability_digest` (SHA-256 of the token) but **not** the raw token when the digest is present. The live token exists in process memory for API responses and auth; it is reloaded from Redis by `skillId` + digest on other workers.
- **Fulfillment:** after a successful settle with a **tx id** in `receipts[]`, expensive work runs once per task (guarded by `a2a:fulfill:lock:{task_id}` on Redis). Safe **retries** reuse the receipt and skip `verify+settle` (no double settlement in-process). If settle returns success **without** a tx id, the server keeps the task `input-required` (no unpaid expensive execution).

## Notifications

The Google A2A JSON-RPC surface in this repo does **not** expose push/subscription for task completion. Clients should **poll `tasks/get`** (or hold a single in-flight continuation) until `completed` / `failed`. Push would require an explicit protocol extension — deferred.

## Limitations (lifecycle)

- Without `REDIS_URL` (or when Redis is down and `A2A_TASK_STORE_REDIS=true` cannot connect), tasks stay **in-process only** — same as legacy behavior on restart.
- Paid continuation still requires the capability token in `message.metadata`; the digest in Redis proves ownership server-side after restart when durability is enabled.
