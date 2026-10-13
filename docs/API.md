# API Reference

**Purpose:** Every endpoint of the Flask API with request bodies, real response examples, status codes and curl commands.

## Overview

The API is JSON over HTTP under `/api`. Authenticated endpoints need `Authorization: Bearer <access_token>` from login or register. Every error is `{"error": "..."}`, with a `details` object added for validation errors.

The response examples below are real responses captured from the running app on 2026-10-13 (tokens shortened). Timestamps from the development SQLite database have no UTC offset; on Postgres they end in `+00:00`.

## Table of Contents

- [Conventions](#conventions)
- [Health](#health)
- [Auth](#auth): register, login, me
- [Chat](#chat): sessions, messages, streaming, history
- [Portfolio](#portfolio): holdings and live quotes
- [Admin](#admin): users, unlock, audit logs
- [Endpoint summary](#endpoint-summary)

## Conventions

```bash
BASE=http://127.0.0.1:5000/api      # dev; Docker: http://localhost:8080/api
TOKEN=<access_token from login>
```

| Status | Meaning |
|---|---|
| 200 / 201 / 204 | OK / created / deleted (empty body) |
| 400 | Validation failed: `{"error": "Invalid input", "details": {...}}` |
| 401 | Missing, invalid or expired token, or wrong credentials |
| 403 | Account locked, or admin required |
| 404 | Not found, **or owned by another user** |
| 409 | Duplicate (email or symbol) |
| 429 | Rate limited. Includes `Retry-After` and `X-RateLimit-*` headers |
| 503 | Gemini unavailable (plain message endpoint only) |

Rate-limited response (captured after 11 rapid logins):

```http
HTTP/1.1 429 TOO MANY REQUESTS
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
Retry-After: 59

{"error": "Too many requests (10 per 1 minute). Please wait a moment and try again."}
```

## Health

### `GET /api/health`

No auth, not rate limited. Used by Docker and Render health checks.

```bash
curl $BASE/health
```

```json
{"status": "ok"}
```

## Auth

### `POST /api/auth/register`

Rate limited per IP (`AUTH_RATE_LIMIT`). Returns a token, so the user is logged in immediately.

| Field | Type | Rules |
|---|---|---|
| `email` | string | required, valid email, stored lowercase |
| `password` | string | required, 8–128 characters |
| `full_name` | string | optional, max 120 |

```bash
curl -X POST $BASE/auth/register -H "Content-Type: application/json" \
  -d '{"email":"jordan@example.com","password":"demo-pass-123","full_name":"Jordan Lee"}'
```

`201 Created`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.…",
  "user": {
    "account_locked": false,
    "created_at": "2026-10-13T04:50:59.155017",
    "email": "jordan@example.com",
    "full_name": "Jordan Lee",
    "id": 1,
    "is_admin": false
  }
}
```

`400` for invalid input:

```json
{
  "details": {
    "email": ["Not a valid email address."],
    "password": ["Length must be between 8 and 128."]
  },
  "error": "Invalid input"
}
```

`409` `{"error": "Email is already registered"}`

### `POST /api/auth/login`

Rate limited per IP. After 5 wrong passwords in a row the account is locked until an admin unlocks it.

```bash
curl -X POST $BASE/auth/login -H "Content-Type: application/json" \
  -d '{"email":"jordan@example.com","password":"demo-pass-123"}'
```

`200 OK`: same shape as register.

| Status | Body |
|---|---|
| 401 | `{"error": "Invalid email or password"}` (same for unknown email and wrong password) |
| 403 | `{"error": "Account is locked"}` |

### `GET /api/auth/me`

```bash
curl $BASE/auth/me -H "Authorization: Bearer $TOKEN"
```

`200 OK`

```json
{
  "user": {
    "account_locked": false,
    "created_at": "2026-10-13T04:50:59.155017",
    "email": "jordan@example.com",
    "full_name": "Jordan Lee",
    "id": 1,
    "is_admin": false
  }
}
```

Without a token: `401` `{"error": "Missing Authorization Header"}`. Expired: `401` `{"error": "Token has expired"}`.

## Chat

All chat endpoints require a token. Users can only see their own sessions and conversations; anything else returns 404.

### `POST /api/chat/session`

Creates a session and its first conversation. Body is optional: `{"title": "..."}` (max 200). Untitled sessions are named after their first message.

```bash
curl -X POST $BASE/chat/session -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{}'
```

`201 Created`

```json
{
  "conversation_id": 1,
  "session": {
    "conversation_ids": [1],
    "created_at": "2026-10-13T04:51:08.698829",
    "id": 1,
    "title": null
  }
}
```

### `GET /api/chat/sessions`

Newest first.

```json
{
  "sessions": [
    {
      "conversation_ids": [2],
      "created_at": "2026-10-13T04:52:07.948115",
      "id": 2,
      "title": "How diversified is my portfolio?"
    },
    {
      "conversation_ids": [1],
      "created_at": "2026-10-13T04:51:08.698829",
      "id": 1,
      "title": "In two sentences: what is an index fund?"
    }
  ]
}
```

### `POST /api/chat/message`

Sends a message and waits for the full reply. Rate limited per user (`CHAT_RATE_LIMIT`, shared with the streaming endpoint). Both messages are saved together; if Gemini fails nothing is saved.

| Field | Type | Rules |
|---|---|---|
| `conversation_id` | int | required, must belong to you |
| `content` | string | required, 1–4000 characters |

```bash
curl -X POST $BASE/chat/message -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":1,"content":"In two sentences: what is an index fund?"}'
```

`201 Created` (real Gemini reply)

```json
{
  "assistant_message": {
    "content": "An index fund is a type of mutual fund or Exchange Traded Fund (ETF) designed to track the performance of a specific market index, like the S&P 500 or a total stock market index. By holding a diversified collection of investments that mirror the chosen index, it offers broad market exposure and generally comes with lower fees compared to actively managed funds.",
    "created_at": "2026-10-13T04:51:27.606159",
    "id": 2,
    "role": "assistant"
  },
  "user_message": {
    "content": "In two sentences: what is an index fund?",
    "created_at": "2026-10-13T04:51:21.626647",
    "id": 1,
    "role": "user"
  }
}
```

| Status | Body |
|---|---|
| 404 | `{"error": "Conversation not found"}` |
| 503 | e.g. `{"error": "The advisor is getting too many requests right now. Please wait a minute and try again."}` |

### `POST /api/chat/message/stream`

Same body and rate limit as `/message`, but the response is `text/event-stream`. Each event is one `data: <json>` line followed by a blank line:

| Event | Fields | When |
|---|---|---|
| `delta` | `text` | Each chunk of the reply |
| `done` | `user_message`, `assistant_message` | Both messages saved; stream ends |
| `error` | `error` | Gemini failed; nothing saved; stream ends |

Errors before the stream starts (validation, 404, 429) come back as normal JSON responses.

```bash
curl -N -X POST $BASE/chat/message/stream -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":1,"content":"In one sentence: what is a bond?"}'
```

Real output:

```text
data: {"type": "delta", "text": "A bond is essentially a loan made by an investor to a borrower—typically a corporation or government—in"}

data: {"type": "delta", "text": " exchange for periodic interest payments and the return of the principal amount on a specified maturity date."}

data: {"type": "done", "user_message": {"id": 3, "role": "user", "content": "In one sentence: what is a bond?", "created_at": "2026-10-13T04:51:27.729644"}, "assistant_message": {"id": 4, "role": "assistant", "content": "A bond is essentially a loan made by an investor to a borrower—typically a corporation or government—in exchange for periodic interest payments and the return of the principal amount on a specified maturity date.", "created_at": "2026-10-13T04:51:29.318128"}}
```

### `GET /api/chat/history/<conversation_id>`

```json
{
  "conversation_id": 1,
  "messages": [
    {"id": 1, "role": "user", "content": "In two sentences: what is an index fund?", "created_at": "..."},
    {"id": 2, "role": "assistant", "content": "An index fund is ...", "created_at": "..."}
  ]
}
```

`404` `{"error": "Conversation not found"}` for unknown IDs or another user's conversation.

### `DELETE /api/chat/session/<session_id>`

Deletes the session with its conversations and messages. `204 No Content`, or `404` `{"error": "Session not found"}`.

## Portfolio

All portfolio endpoints require a token. The portfolio is created on first access.

### `GET /api/portfolio/`

Note the trailing slash. Quantities and costs are decimal strings.

```bash
curl $BASE/portfolio/ -H "Authorization: Bearer $TOKEN"
```

```json
{
  "portfolio": {
    "holdings": [
      {"average_cost": "172.3000", "id": 2, "quantity": "15.000000", "symbol": "AAPL"},
      {"average_cost": "72.1000",  "id": 3, "quantity": "60.000000", "symbol": "BND"},
      {"average_cost": "325.0000", "id": 4, "quantity": "10.000000", "symbol": "MSFT"},
      {"average_cost": "215.5000", "id": 1, "quantity": "40.000000", "symbol": "VTI"}
    ],
    "id": 1,
    "name": "My Portfolio"
  }
}
```

### `GET /api/portfolio/quotes`

Live prices for your holdings from Yahoo Finance, cached 60 seconds. A symbol Yahoo doesn't know maps to `null`. `enabled` is `false` when `QUOTES_ENABLED=false` (then `quotes` is `{}`).

```json
{
  "enabled": true,
  "quotes": {
    "AAPL": {"currency": "USD", "previous_close": 336.64, "price": 340.97},
    "BND":  {"currency": "USD", "previous_close": 70.22,  "price": 70.25},
    "MSFT": {"currency": "USD", "previous_close": 535.07, "price": 541.15},
    "VTI":  {"currency": "USD", "previous_close": 381.9,  "price": 381.57}
  }
}
```

### `POST /api/portfolio/holding`

| Field | Type | Rules |
|---|---|---|
| `symbol` | string | required, 1–16 of `A-Z a-z . -`, stored uppercase |
| `quantity` | decimal | required, > 0 |
| `average_cost` | decimal | required, ≥ 0 |

```bash
curl -X POST $BASE/portfolio/holding -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"vti","quantity":"40","average_cost":"215.50"}'
```

`201 Created`

```json
{"holding": {"average_cost": "215.5000", "id": 1, "quantity": "40.000000", "symbol": "VTI"}}
```

`409` `{"error": "VTI is already in the portfolio; update it instead"}`

### `PUT /api/portfolio/holding/<holding_id>`

Body: `quantity` and `average_cost` (same rules). The symbol can't be changed.

```bash
curl -X PUT $BASE/portfolio/holding/4 -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"quantity":"10","average_cost":"325.00"}'
```

```json
{"holding": {"average_cost": "325.0000", "id": 4, "quantity": "10.000000", "symbol": "MSFT"}}
```

### `DELETE /api/portfolio/holding/<holding_id>`

`204 No Content`, or `404` `{"error": "Holding not found"}`.

## Admin

Requires a token for a user with `is_admin`. Others get `403` `{"error": "Admin access required"}`. List endpoints take `page` (default 1) and `per_page` (default 50, max 200).

### `GET /api/admin/users`

```bash
curl "$BASE/admin/users?page=1" -H "Authorization: Bearer $ADMIN_TOKEN"
```

`?per_page=2` (real output):

```json
{
  "page": 1,
  "total": 3,
  "users": [
    {
      "account_locked": false,
      "created_at": "2026-10-13T04:50:59.155017",
      "email": "jordan@example.com",
      "full_name": "Jordan Lee",
      "id": 1,
      "is_admin": false
    },
    {
      "account_locked": false,
      "created_at": "2026-10-13T04:50:59.444654",
      "email": "admin@example.com",
      "full_name": "Site Admin",
      "id": 2,
      "is_admin": true
    }
  ]
}
```

### `POST /api/admin/users/<user_id>/unlock`

Clears the lock and the failed-login counter, and writes an `account_unlocked` audit entry. Returns `{"user": {...}}`.

### `GET /api/admin/audit-logs`

Newest first. Optional filters: `user_id`, `action`.

Actions: `register`, `login`, `login_failed`, `login_blocked_locked`, `account_unlocked`, `holding_added`, `holding_updated`, `holding_deleted`.

```bash
curl "$BASE/admin/audit-logs?action=login_failed&per_page=2" -H "Authorization: Bearer $ADMIN_TOKEN"
```

```json
{
  "audit_logs": [
    {
      "action": "login_failed",
      "created_at": "2026-10-13T04:53:56.013372",
      "details": null,
      "id": 29,
      "ip_address": "127.0.0.1",
      "user_id": 1
    },
    {
      "action": "login_failed",
      "created_at": "2026-10-13T04:53:11.939765",
      "details": null,
      "id": 24,
      "ip_address": "127.0.0.1",
      "user_id": 1
    }
  ],
  "page": 1,
  "total": 9
}
```

## Endpoint summary

| Method | Path | Auth | Rate limit |
|---|---|---|---|
| GET | `/api/health` | none | exempt |
| POST | `/api/auth/register` | none | per IP |
| POST | `/api/auth/login` | none | per IP |
| GET | `/api/auth/me` | JWT | |
| POST | `/api/chat/session` | JWT | |
| GET | `/api/chat/sessions` | JWT | |
| POST | `/api/chat/message` | JWT | per user (shared) |
| POST | `/api/chat/message/stream` | JWT | per user (shared) |
| GET | `/api/chat/history/<conversation_id>` | JWT | |
| DELETE | `/api/chat/session/<session_id>` | JWT | |
| GET | `/api/portfolio/` | JWT | |
| GET | `/api/portfolio/quotes` | JWT | |
| POST | `/api/portfolio/holding` | JWT | |
| PUT | `/api/portfolio/holding/<holding_id>` | JWT | |
| DELETE | `/api/portfolio/holding/<holding_id>` | JWT | |
| GET | `/api/admin/users` | admin | |
| POST | `/api/admin/users/<user_id>/unlock` | admin | |
| GET | `/api/admin/audit-logs` | admin | |

## See Also

- [SECURITY.md](SECURITY.md) for auth, rate limiting and ownership rules
- [BACKEND.md](BACKEND.md#routes) for where each route lives
- `backend/scripts/smoke_test.ps1` for a scripted walkthrough of these endpoints

---
**Last Updated:** 2026-10-13
**Status:** Complete
