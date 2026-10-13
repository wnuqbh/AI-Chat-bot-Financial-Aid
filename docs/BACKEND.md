# Backend

**Purpose:** Guide to the Flask API codebase in `backend/`: where things are, how they work, and how to do common tasks.

## Overview

The backend is a Flask 3 app built with an app factory. It uses Flask-SQLAlchemy with Alembic migrations, Flask-JWT-Extended for auth, marshmallow for input validation, Flask-Limiter for rate limits, the `google-genai` SDK for Gemini, and `yfinance` for prices. In production it runs under gunicorn.

## Table of Contents

- [Project structure](#project-structure)
- [App factory](#app-factory)
- [Configuration](#configuration)
- [Models](#models)
- [Routes](#routes)
- [Services](#services)
- [Middleware](#middleware)
- [Error handling](#error-handling)
- [Conventions](#conventions)
- [Common tasks](#common-tasks)

## Project structure

```
backend/
├── main.py                  # Entry point: create_app(); `python main.py` migrates then runs the dev server
├── config.py                # Development / Production / Testing config classes
├── requirements.txt
├── .env.example             # Copy to .env
├── Dockerfile               # python:3.13-slim, runs as non-root appuser
├── docker-entrypoint.sh     # db upgrade, then gunicorn (gthread)
├── app/
│   ├── __init__.py          # create_app(), db, jwt, limiter, migrate, error handlers, make-admin CLI
│   ├── models/__init__.py   # All SQLAlchemy models
│   ├── schemas/__init__.py  # marshmallow request schemas
│   ├── middleware/__init__.py  # current_user_id, admin_required, rate-limit helpers
│   ├── routes/
│   │   ├── auth.py          # /api/auth
│   │   ├── chat.py          # /api/chat
│   │   ├── portfolio.py     # /api/portfolio
│   │   └── admin.py         # /api/admin
│   └── services/
│       ├── advisor.py       # Gemini prompt building, calls, retries, streaming
│       ├── quotes.py        # Yahoo Finance prices with a 60s cache
│       └── audit.py         # record_audit()
├── migrations/              # Alembic (Flask-Migrate)
├── scripts/
│   ├── chat.ps1             # Interactive terminal chat client
│   └── smoke_test.ps1       # End-to-end check against a running server
└── tests/                   # pytest
```

## App factory

`app/__init__.py` `create_app(config_name=None)`:

1. Picks the config class from `FLASK_ENV` (default `development`) and runs its `validate()` if it has one.
2. Wraps the app in `ProxyFix` when `TRUSTED_PROXY_COUNT > 0`, so `request.remote_addr` is the real client IP behind nginx or Render.
3. Initialises `db`, `migrate` (with `render_as_batch=True` so migrations can alter columns on SQLite), `jwt`, `limiter` and CORS.
4. Registers the four blueprints and `GET /api/health`.
5. Registers JSON error handlers and the `make-admin` CLI command.

## Configuration

All settings are in `config.py` and read from environment variables (loaded from `backend/.env` by python-dotenv). A blank value in `.env` counts as unset.

| Variable | Default | Meaning |
|---|---|---|
| `FLASK_ENV` | `development` | `development`, `production` or `testing` |
| `DATABASE_URL` | `sqlite:///dev.db` | `postgres://` and `postgresql://` are rewritten to `postgresql+psycopg://` |
| `GEMINI_API_KEY` | none | Required for chat |
| `GEMINI_MODEL` | `gemini-2.5-flash` | |
| `GEMINI_MAX_OUTPUT_TOKENS` | `8192` | Includes 2.5 models' thinking tokens, so keep it generous |
| `JWT_SECRET_KEY` | dev value | Required, 32+ chars, in production |
| `SECRET_KEY` | dev value | Required in production |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated |
| `CHAT_RATE_LIMIT` | `10 per minute;200 per day` | Per user, shared by both message endpoints |
| `AUTH_RATE_LIMIT` | `10 per minute` | Per IP, login and register |
| `RATELIMIT_STORAGE_URI` | `memory://` | Use `redis://...` with several workers |
| `TRUSTED_PROXY_COUNT` | `0` | Number of reverse proxies in front |
| `QUOTES_ENABLED` | `true` | Turn live prices off |

Fixed in code: token lifetime 1 hour, `BCRYPT_ROUNDS = 12`, `MAX_FAILED_LOGINS = 5`, `CHAT_HISTORY_LIMIT = 20`, `GEMINI_RETRY_DELAYS = (1, 3)`, `QUOTES_CACHE_SECONDS = 60`.

`ProductionConfig.validate()` refuses to start without `JWT_SECRET_KEY`, `SECRET_KEY` and `DATABASE_URL`. `TestingConfig` uses in-memory SQLite, 4 bcrypt rounds, no quotes and no retry delays.

## Models

All in `app/models/__init__.py`. See the diagram in [ARCHITECTURE.md](ARCHITECTURE.md#database-schema).

| Model | Table | Notes |
|---|---|---|
| `User` | `users` | `to_dict()` never includes `password_hash` |
| `ChatSession` | `sessions` | `to_dict()` includes `conversation_ids` |
| `Conversation` | `conversations` | `messages` ordered by `Message.id` |
| `Message` | `messages` | `role` is `"user"` or `"assistant"` |
| `Portfolio` | `portfolios` | One per user (`user_id` unique) |
| `Holding` | `holdings` | Unique `(portfolio_id, symbol)`; quantity and cost are `Numeric`, serialised as strings |
| `AuditLog` | `audit_logs` | No relationship to `User` on purpose |

Timestamps use the `utcnow()` helper (timezone-aware UTC).

## Routes

| File | Endpoints |
|---|---|
| `routes/auth.py` | `POST /register`, `POST /login`, `GET /me` |
| `routes/chat.py` | `POST /session`, `GET /sessions`, `POST /message`, `POST /message/stream`, `GET /history/<id>`, `DELETE /session/<id>` |
| `routes/portfolio.py` | `GET /`, `GET /quotes`, `POST /holding`, `PUT /holding/<id>`, `DELETE /holding/<id>` |
| `routes/admin.py` | `GET /users`, `POST /users/<id>/unlock`, `GET /audit-logs` |

Request and response details: [API.md](API.md).

The chat message endpoints share `_start_exchange` / `_finish_exchange`, which stage the user's message and commit it together with the reply. `stream_message` can't use the request's DB session inside its generator (see [ARCHITECTURE.md](ARCHITECTURE.md#chat-data-flow)), so it builds the Gemini request first and re-loads the conversation by ID when saving.

## Services

### `services/advisor.py`

- `SYSTEM_PROMPT`: frames the model as a financial *education* assistant that is not a licensed advisor.
- `build_request(messages, portfolio)`: turns history (last 20 messages) and holdings with live prices into `generate_content` arguments. Stored role `assistant` becomes Gemini's `model`.
- `generate_reply(messages, portfolio)`: one-shot reply, used by `POST /message`.
- `stream_reply(request)`: yields text chunks, used by `POST /message/stream`.
- Retries 429/500/502/503/504 with `GEMINI_RETRY_DELAYS`. Streams retry only before any text was sent.
- If Gemini stops at the token limit, appends *"(This answer was cut off because it hit the length limit.)"*.
- All failures raise `AdvisorUnavailableError` with a message safe to show users. Routes turn it into a 503 (plain) or an `error` event (stream).

### `services/quotes.py`

- `get_quotes(symbols)` returns `{symbol: {"price", "previous_close", "currency"} | None}` and never raises.
- Missing symbols are fetched in parallel (up to 8 threads) and cached for 60 seconds per process.
- Returns `{}` when `QUOTES_ENABLED=false`.
- To switch to a licensed data provider, replace `_fetch_quote`.

### `services/audit.py`

`record_audit(action, user_id=None, details=None)` adds an `AuditLog` row with the client IP to the current transaction. The caller commits.

## Middleware

`app/middleware/__init__.py`:

- `current_user_id()`: the JWT subject as an `int`. Use this, not `get_jwt_identity()` directly.
- `@admin_required`: verifies the JWT and that the user has `is_admin`, else 403.
- `user_rate_limit_key()`: `user:<id>` when logged in, else client IP.
- `chat_rate_limit()` / `auth_rate_limit()`: read the limit strings from config at request time.

## Error handling

Every error response is JSON `{"error": "..."}`:

| Source | Status | Body |
|---|---|---|
| marshmallow `ValidationError` | 400 | `{"error": "Invalid input", "details": {field: [messages]}}` |
| `abort(code, description=...)` | code | `{"error": description}` |
| Rate limit | 429 | `{"error": "Too many requests (10 per 1 minute). Please wait a moment and try again."}` |
| JWT missing / invalid / expired | 401 | `{"error": "..."}` |
| Unhandled exception | 500 | `{"error": "Internal server error"}`, logged with traceback, session rolled back |

## Conventions

- **Ownership:** every query for a user-owned resource filters by the JWT user, joining through parents (`_get_owned_conversation`, `_get_owned_holding`). Another user's resource returns **404, not 403**, so IDs can't be probed.
- **Validation:** `XSchema().load(request.get_json(silent=True) or {})`.
- **Audit:** call `record_audit(...)` before `db.session.commit()` so the log and the change are saved together.
- **Tests never call Gemini or Yahoo** (see [TESTING.md](TESTING.md)).

## Common tasks

### Add a model field

```bash
# 1. edit app/models/__init__.py
flask --app main db migrate -m "add risk_profile to users"
# 2. review the file in migrations/versions/, then
flask --app main db upgrade
pytest tests/test_migrations.py
```

Commit the migration file. Deploys apply it automatically (`docker-entrypoint.sh` runs `db upgrade`).

### Add an endpoint

```python
# app/routes/portfolio.py
@portfolio_bp.get("/summary")
@jwt_required()
def summary():
    portfolio = _get_or_create_portfolio(current_user_id())
    db.session.commit()
    return jsonify({"holdings": len(portfolio.holdings)})
```

Add a marshmallow schema in `app/schemas/` for any request body, a test in `tests/`, and an entry in [API.md](API.md).

### Chat from the terminal

```powershell
.\scripts\chat.ps1
```

### Grant or revoke admin

```bash
flask --app main make-admin you@example.com
flask --app main make-admin you@example.com --revoke
```

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) for the request flows
- [API.md](API.md) for endpoint details
- [SECURITY.md](SECURITY.md) for auth and rate limiting

---
**Last Updated:** 2026-10-13
**Status:** Complete
