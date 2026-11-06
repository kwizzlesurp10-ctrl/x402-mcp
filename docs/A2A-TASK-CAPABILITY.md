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

Deploy the previous release; no data migration (in-memory task store is ephemeral).

## Limitations (lifecycle)

- Tasks live in an **in-memory** store (`app/a2a_rpc.py`). Restart drops all tasks, capability tokens, and payment-continuation context; clients must start new tasks.
- Paid continuation (`x402.payment.payload`) requires the capability token in message metadata; this **does not** persist across server restarts.
- Horizontal scaling without a shared task store is unsupported: each instance has its own task namespace.
