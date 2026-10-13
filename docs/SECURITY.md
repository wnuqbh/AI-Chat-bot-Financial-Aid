# Security

**Purpose:** How the app protects accounts and data, which controls exist and where they are in the code, and which known gaps remain.

## Overview

Users authenticate with email and password, receive a short-lived JWT, and can only reach their own data. Logins and chat are rate limited, every request body is validated, and security-relevant events are written to an audit log that admins can read. The app is for financial *education* and stores no payment or bank data.

## Table of Contents

- [Authentication (JWT)](#authentication-jwt)
- [Passwords](#passwords)
- [Account lockout](#account-lockout)
- [Authorization and roles](#authorization-and-roles)
- [Rate limiting](#rate-limiting)
- [Input validation](#input-validation)
- [SQL injection](#sql-injection)
- [XSS](#xss)
- [CORS](#cors)
- [Audit logging](#audit-logging)
- [Secrets and configuration](#secrets-and-configuration)
- [Data privacy](#data-privacy)
- [Known gaps and recommendations](#known-gaps-and-recommendations)

## Authentication (JWT)

| Setting | Value | Where |
|---|---|---|
| Library | Flask-JWT-Extended | `app/__init__.py` |
| Algorithm | HS256, signed with `JWT_SECRET_KEY` | `config.py` |
| Lifetime | 1 hour (`JWT_ACCESS_TOKEN_EXPIRES`) | `config.py` |
| Subject | `str(user.id)` | `routes/auth.py` |
| Refresh tokens | none: users log in again | |
| Client storage | `localStorage["advisor_token"]` | `frontend/src/api.ts` |

- Protected routes use `@jwt_required()`. Read the user with `current_user_id()` from `app/middleware`.
- Expired, malformed and missing tokens all return `401` with a JSON error. The frontend logs out on any 401 and shows "Your session expired. Please log in again."
- There is no server-side token revocation. To invalidate **every** token at once, change `JWT_SECRET_KEY`.
- In production `JWT_SECRET_KEY` must be set and at least 32 characters, or the app refuses to start (`ProductionConfig.validate()`).

## Passwords

- Hashed with **bcrypt**, 12 rounds (`BCRYPT_ROUNDS`; 4 in tests for speed).
- Length 8–128 characters, enforced by `RegisterSchema`.
- The hash is never returned: `User.to_dict()` leaves it out.
- Login returns the same message, `Invalid email or password`, whether the email is unknown or the password is wrong.

## Account lockout

- Each wrong password increments `failed_login_attempts`. At `MAX_FAILED_LOGINS` (5) the account is locked.
- A successful login resets the counter.
- A locked account is refused with `403 Account is locked`, **even with the correct password**, and the attempt is logged as `login_blocked_locked`.
- Only an admin can unlock (Admin → Users → **Unlock**, or `POST /api/admin/users/<id>/unlock`), which also resets the counter.

![Locked account at login](screenshots/login-locked.png)

![Admin users list with a locked account](screenshots/admin-users.png)

## Authorization and roles

Two roles, stored as `users.is_admin`:

| Role | Can |
|---|---|
| User | Their own chats, messages and portfolio |
| Admin | Everything a user can, plus list users, unlock accounts, read the audit log |

- Admin endpoints use `@admin_required`, which re-reads the user from the database on every request. Revoking admin takes effect immediately; it doesn't wait for the token to expire.
- Admin is granted only from the command line: `flask --app main make-admin <email>` (`--revoke` to remove). There is no API to grant it.
- The frontend hides the Admin tab and route for non-admins, but the backend check is what enforces it. A non-admin calling an admin endpoint gets `403 Admin access required`.

**Ownership rule:** every query for a user-owned resource filters by the JWT user, joining through parent tables:

```python
# routes/chat.py
Conversation.query.join(ChatSession).filter(
    Conversation.id == conversation_id, ChatSession.user_id == user_id
)
```

Another user's resource returns **404, not 403**, so an attacker can't tell which IDs exist. Covered by `test_cannot_access_another_users_conversation`, `test_cannot_modify_another_users_holding` and `test_stream_rejects_other_users_conversation`.

The Gemini request for a user includes only that user's own conversation and holdings, so a prompt can't pull in another user's data.

## Rate limiting

Flask-Limiter, storage from `RATELIMIT_STORAGE_URI`.

| Endpoints | Default | Keyed by |
|---|---|---|
| `POST /auth/login`, `POST /auth/register` | `10 per minute` | client IP |
| `POST /chat/message` + `POST /chat/message/stream` (one shared allowance) | `10 per minute;200 per day` | user ID |
| `GET /health` | exempt | |
| everything else | none | |

- Limits are configurable through `AUTH_RATE_LIMIT` and `CHAT_RATE_LIMIT` without code changes.
- Responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and `Retry-After` on 429.
- With more than one gunicorn worker or instance, storage **must** be Redis; with `memory://` each process counts separately. Compose and Render use Redis.
- Behind a proxy, set `TRUSTED_PROXY_COUNT` to the number of proxies. Otherwise every request appears to come from the proxy's IP and all users share one login allowance. Set it too high and clients can spoof their IP with `X-Forwarded-For`.

The chat limit also caps Gemini spending per user.

## Input validation

Every request body goes through a marshmallow schema in `app/schemas/__init__.py`; unknown fields are rejected.

| Schema | Rules |
|---|---|
| `RegisterSchema` | valid email; password 8–128; name ≤ 120 |
| `LoginSchema` | valid email; password required |
| `MessageSchema` | `conversation_id` int; `content` 1–4000 characters |
| `HoldingSchema` | symbol `^[A-Za-z.\-]{1,16}$`; quantity > 0; average cost ≥ 0 (decimals) |
| `CreateSessionSchema` | title ≤ 200 |

Failures return `400 {"error": "Invalid input", "details": {...}}`. URL IDs are typed (`<int:...>`) by the routes.

## SQL injection

All database access goes through the SQLAlchemy ORM, which uses bound parameters. The code contains no raw SQL strings (no `text()` or `execute()` with string building).

## XSS

- React escapes all text it renders.
- Advisor replies are rendered with `react-markdown` **without** `rehype-raw`, so HTML inside a reply is shown as text, not executed. Its default URL handling also drops `javascript:` links.
- No `dangerouslySetInnerHTML` anywhere in the frontend.
- Because the JWT is in `localStorage`, any XSS would be able to read it. That's the main reason to keep the points above true. See [known gaps](#known-gaps-and-recommendations).

## CORS

`CORS(app, origins=CORS_ORIGINS)`. Only the listed origins (comma-separated, exact match, no trailing slash) may call the API from a browser. Default `http://localhost:5173`. In development the Vite proxy makes requests same-origin, so CORS doesn't apply. In production set it to your Vercel URL.

## Audit logging

`record_audit()` (`app/services/audit.py`) adds a row in the same transaction as the change it describes.

| Action | When | `details` |
|---|---|---|
| `register` | Account created | |
| `login` | Successful login | |
| `login_failed` | Wrong password for an existing account | |
| `login_blocked_locked` | Login attempt on a locked account | |
| `account_unlocked` | Admin unlocked a user (`user_id` = the admin) | `user <id>` |
| `holding_added` / `holding_updated` / `holding_deleted` | Portfolio change | symbol |

- Each row stores the client IP (real client IP when `TRUSTED_PROXY_COUNT` is set).
- `audit_logs` has no foreign key to `users`, so history survives account deletion.
- Failed logins for **unknown** emails are not logged (there's no user to attach them to); they are still rate limited.
- Chat messages are not audit-logged; they're stored as messages.

![Audit log](screenshots/admin-audit-log.png)

## Secrets and configuration

- Secrets live in `backend/.env` locally (git-ignored) and in the host's environment settings in production. Never commit them.
- Render generates `JWT_SECRET_KEY` and `SECRET_KEY` (`generateValue: true` in `render.yaml`).
- Generate your own with `python -c "import secrets; print(secrets.token_hex(32))"`.
- The development server binds to `127.0.0.1` only, because the Werkzeug debugger allows code execution.
- The backend Docker image runs as a non-root user (`appuser`).

## Data privacy

| Data | Stored where | Sent to |
|---|---|---|
| Email, name, password hash | App database | nobody |
| Chat messages | App database | **Google Gemini** (last 20 messages of the conversation, with each request) |
| Holdings (symbol, quantity, cost) | App database | **Google Gemini** (in the system prompt); **Yahoo Finance** receives symbols only |
| IP addresses | `audit_logs` | nobody |

- Users can delete their own conversations (deleting a session removes its messages).
- There is no self-service account deletion or data export yet.
- Gemini's data handling depends on your Google API terms; free-tier keys may allow Google to use prompts to improve its products. Use a paid key for real user data.
- Every chat screen states that answers are for education, not financial advice, and the system prompt tells the model the same.

## Known gaps and recommendations

| Gap | Risk | Suggested fix |
|---|---|---|
| JWT in `localStorage` | Stolen by any XSS | Move to an `HttpOnly`, `Secure`, `SameSite` cookie (Flask-JWT-Extended supports this, with CSRF protection) |
| No token revocation | A stolen token works for up to 1 hour | Add a token blocklist, or shorten the lifetime and add refresh tokens |
| No security headers | Clickjacking, weaker XSS defence | Add `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy` in `nginx.conf` / `vercel.json` |
| Lockout can be triggered by anyone who knows an email | Denial of service against one account | Time-based unlock, or lock per IP + account; CAPTCHA after failures |
| Email enumeration | `409 Email is already registered` and `403 Account is locked` reveal that an email exists | Generic responses; email verification flow |
| No email verification or password reset | Typos lock users out; admins can't reset passwords | Add a verified-email and reset flow |
| No password strength check beyond length | Weak passwords | Check against a breached-password list |
| Docker Compose uses Postgres password `advisor` | Weak if the port is ever exposed | Change it in `docker-compose.yml` (the port is not published by default) |

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md#authentication-flow) for the login sequence
- [TESTING.md](TESTING.md) for the security-related tests
- [DEPLOYMENT.md](DEPLOYMENT.md) for production secrets

---
**Last Updated:** 2026-10-13
**Status:** Complete
