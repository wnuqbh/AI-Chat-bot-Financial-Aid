# Troubleshooting

**Purpose:** Find the cause and fix for common errors, from local setup to production.

## Overview

Find the message you're seeing (in the browser, terminal or API response) in the sections below. Most problems are a server that isn't running, a missing environment variable, or a proxy or CORS setting. Backend logs are in the terminal running `python main.py`, in `docker compose logs backend`, or in Render's **Logs** tab.

## Table of Contents

- [Backend won't start](#backend-wont-start)
- [Port already in use](#port-already-in-use)
- [Frontend can't reach the backend](#frontend-cant-reach-the-backend)
- [Database errors](#database-errors)
- [Advisor (Gemini) errors](#advisor-gemini-errors)
- [Login and session problems](#login-and-session-problems)
- [Too many requests (429)](#too-many-requests-429)
- [Portfolio prices](#portfolio-prices)
- [Docker](#docker)
- [Production (Render / Vercel / Supabase)](#production-render--vercel--supabase)
- [Tests](#tests)
- [Known issues](#known-issues)

## Backend won't start

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'flask'` | venv not active | `venv\Scripts\Activate.ps1` (PowerShell) or `source venv/Scripts/activate` (Git Bash), then `pip install -r requirements.txt` |
| `running scripts is disabled on this system` when activating | PowerShell execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `RuntimeError: Missing required environment variables for production: JWT_SECRET_KEY, ...` | `FLASK_ENV=production` without secrets | Set `JWT_SECRET_KEY`, `SECRET_KEY`, `DATABASE_URL`, or use `FLASK_ENV=development` locally |
| `RuntimeError: JWT_SECRET_KEY must be at least 32 characters in production` | Short key | `python -c "import secrets; print(secrets.token_hex(32))"` |
| Server stopped after you saved a file | The auto-reloader hit a syntax error | Fix the error, then run `python main.py` again |

## Port already in use

`OSError: [WinError 10048]` or `Address already in use` for port 5000 (backend) or 5173 (frontend). Usually an earlier server is still running.

Windows (PowerShell):

```powershell
netstat -ano | findstr :5000          # last column is the PID
taskkill /PID <pid> /F
```

macOS / Linux:

```bash
lsof -i :5000
kill <pid>
```

Or run on another port: `$env:PORT = "5001"; python main.py`, then start the frontend with `$env:API_PROXY_TARGET = "http://127.0.0.1:5001"; npm run dev`.

## Frontend can't reach the backend

| Symptom | Fix |
|---|---|
| Red banner **"Cannot reach the server. Is the backend running?"** | Start the backend; check http://127.0.0.1:5000/api/health returns `{"status": "ok"}` |
| Vite terminal shows `http proxy error: /api/... ECONNREFUSED` | Same: the backend isn't on the proxy target. Check `API_PROXY_TARGET` |
| Page loads but every call returns 404 HTML | You opened the backend port (5000) instead of the frontend (5173) |

## Database errors

| Error | Cause | Fix |
|---|---|---|
| `sqlite3.OperationalError: no such table: users` | Migrations not applied | `python main.py` applies them on start, or `flask --app main db upgrade` |
| `test_migrations_build_the_current_schema` fails | Model changed without a migration | `flask --app main db migrate -m "describe change"`, review, commit |
| Want a clean dev database | | Stop the server, delete `backend/instance/dev.db`, start it again |
| `connection to server ... failed: Network is unreachable` (Render → Supabase) | Supabase's direct connection is IPv6-only | Use the **Session pooler** connection string |
| `SSL connection is required` | | Add `?sslmode=require` to `DATABASE_URL` |
| `password authentication failed` | `[YOUR-PASSWORD]` placeholder still in the URL, or special characters not URL-encoded | Fix the password; URL-encode `@ : / ?` etc. |

`postgres://` URLs are fine; the app rewrites them to the psycopg 3 driver.

## Advisor (Gemini) errors

These appear in red above the chat input. Your message goes back into the input box and nothing is saved, so you can resend.

| Message | Cause | Fix |
|---|---|---|
| `GEMINI_API_KEY is not configured` | No key in the backend's environment | Set it in `backend/.env` (or Render), restart |
| `The advisor is getting too many requests right now. Please wait a minute and try again.` | Gemini returned 429 three times (after 1s and 3s retries). Common on free keys | Wait; lower `CHAT_RATE_LIMIT`; use a paid key |
| `The advisor is temporarily overloaded. Please try again in a moment.` | Gemini returned 5xx three times | Wait and retry; Google-side |
| `The advisor service is unavailable` | Non-retryable error, usually an invalid or revoked key, or a wrong `GEMINI_MODEL` | Check the backend log for the Gemini error; fix the key or model name |
| `The advisor returned an empty response` | Gemini returned no text (e.g. safety block) | Rephrase the question |
| Answer ends with *"(This answer was cut off because it hit the length limit.)"* | Hit `GEMINI_MAX_OUTPUT_TOKENS`; 2.5 models spend part of it on thinking | Raise `GEMINI_MAX_OUTPUT_TOKENS` (default 8192) |
| `The connection closed before the reply finished` | Stream cut off: proxy timeout, server restart, network drop | Resend. Behind nginx keep `proxy_buffering off` and `proxy_read_timeout 120s` |
| `This conversation was deleted` | Chat was deleted in another tab while the reply streamed | Start a new chat |

## Login and session problems

| Symptom | Cause | Fix |
|---|---|---|
| `Invalid email or password` | Wrong email or password | Check both; after 5 wrong passwords the account locks |
| `Account is locked` | 5 failed logins in a row | An admin unlocks it in **Admin → Users → Unlock**. Correct passwords don't work until then |
| "Your session expired. Please log in again." | Tokens last 1 hour | Log in again |
| Everyone was logged out at once | `JWT_SECRET_KEY` changed (or wasn't set and differs between restarts/instances) | Expected after rotation; otherwise set a fixed key |
| No **Admin** tab after `make-admin` | The page still has the old user details | Log out and back in |
| `No user with email ...` from `make-admin` | User hasn't registered, or you're pointing at another database | Register first; check `DATABASE_URL` |

**The only admin is locked out:** from `backend/` with the venv active (and `DATABASE_URL` pointing at the right database):

```bash
flask --app main shell
>>> from app import db
>>> from app.models import User
>>> u = User.query.filter_by(email="admin@example.com").first()
>>> u.account_locked = False; u.failed_login_attempts = 0
>>> db.session.commit()
```

## Too many requests (429)

`Too many requests (10 per 1 minute). Please wait a moment and try again.`

- **Login / register:** 10 per minute per IP. Wait for the time in the `Retry-After` header.
- **Chat:** 10 per minute and 200 per day per user, shared by both message endpoints.
- **Everyone hits the login limit at once in production:** all requests look like they come from the proxy. Set `TRUSTED_PROXY_COUNT` to the number of proxies (1 on Render or Compose, 2 with an extra proxy such as Caddy in front).
- **Limits seem higher than configured with several workers:** `RATELIMIT_STORAGE_URI` is `memory://`; use Redis.
- Change limits with `CHAT_RATE_LIMIT` and `AUTH_RATE_LIMIT`, e.g. `20 per minute;500 per day`.

## Portfolio prices

| Symptom | Cause | Fix |
|---|---|---|
| Price column shows `n/a` for one holding | Yahoo doesn't know the symbol, or the fetch failed | Check the ticker on finance.yahoo.com; non-US tickers need a suffix (e.g. `SHOP.TO`) |
| "Could not load live prices right now; values use the prices you paid." | Quotes request failed | Click **Refresh prices**; check the backend's internet access |
| "Live prices are turned off, so values use the prices you paid." | `QUOTES_ENABLED=false` | Set it to `true` and restart |
| Price doesn't change after Refresh | Prices are cached for 60 seconds per server process, and Yahoo itself may be delayed | Wait a minute |
| Symbol rejected | Only letters, `.` and `-`, up to 16 characters | Use the plain ticker |
| `VTI is already in the portfolio; update it instead` | One row per symbol | Use **Edit** on the existing row |

## Docker

| Error | Cause | Fix |
|---|---|---|
| `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` | Docker Desktop isn't running | Start Docker Desktop and wait until it says running |
| `backend` exits right away; log shows `Missing required environment variables` | `backend/.env` lacks `JWT_SECRET_KEY` / `SECRET_KEY` (Compose runs in production mode) | Set both, `docker compose up --build` |
| `frontend` waits forever | Backend health check failing | `docker compose logs backend` |
| Chat reply appears all at once instead of streaming | A proxy is buffering | nginx needs `proxy_buffering off` (already in `frontend/nginx.conf`); the backend also sends `X-Accel-Buffering: no` |
| Code changes don't show up | Images are built once | `docker compose up --build` |
| Start from an empty database | | `docker compose down -v` (**deletes all data** in the `pgdata` volume) |

## Production (Render / Vercel / Supabase)

| Symptom | Cause | Fix |
|---|---|---|
| Browser console: `blocked by CORS policy` | `CORS_ORIGINS` doesn't exactly match the Vercel URL | Set it to the exact origin, `https://...vercel.app`, no trailing slash; Render redeploys |
| Frontend calls `/api/...` on vercel.app and gets 404 or HTML | `VITE_API_URL` not set at build time | Set it in Vercel to `https://<render-url>/api` and **redeploy** |
| First request takes about a minute | Free Render services sleep after 15 minutes idle | Expected on the free plan |
| Deep link like `/chat/12` returns 404 on Vercel | Missing SPA rewrite | `frontend/vercel.json` must be deployed (Root Directory = `frontend`) |
| `/api/health` fails on Render | Startup error | Render → Logs; usually `DATABASE_URL` or missing secrets |

## Tests

| Symptom | Fix |
|---|---|
| A backend test tries to reach Gemini | Add the `fake_advisor` or `fake_stream` fixture to it |
| Frontend test fails with `Unexpected request: GET /something` | Add that route to the test's `fakeServer({...})` |
| `npm run build` fails but `npm test` passes | The build type-checks test files too; fix the TypeScript error it reports |

## Known issues

- **Times in the admin panel are off by your UTC offset in development.** SQLite doesn't store the timezone, so the API returns timestamps like `2026-10-13T04:53:56` without `+00:00`, and the browser reads them as local time. Postgres (Docker and production) returns `+00:00` and displays correctly. A fix would be to add the UTC offset when serialising naive datetimes in the models' `to_dict()`.

## See Also

- [SETUP.md](SETUP.md) for setup steps
- [DEPLOYMENT.md](DEPLOYMENT.md) for production configuration
- [SECURITY.md](SECURITY.md) for lockout and rate-limit behaviour

---
**Last Updated:** 2026-10-13
**Status:** Complete
