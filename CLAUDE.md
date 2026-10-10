# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Financial Advisor AI Chatbot

Full-stack conversational app where retail investors get financial guidance from an LLM (Google Gemini), with answers informed by their holdings and live market prices.

**Status (Oct 2026):** Feature-complete and running locally and in Docker Compose. Deployment config for Supabase + Render + Vercel is in place (`docs/DEPLOYMENT.md`) but not yet deployed. Git branch is `main`; CI is in `.github/workflows/ci.yml`.

## Commands

### Backend

Run from `backend/` with the venv active (`venv\Scripts\Activate.ps1` in PowerShell, `source venv/Scripts/activate` in Git Bash on this machine).

```bash
pip install -r requirements.txt
cp .env.example .env          # then set GEMINI_API_KEY
python main.py                # dev server on http://127.0.0.1:5000; applies migrations first

pytest                                                      # all tests
pytest tests/test_chat.py                                   # one file
pytest tests/test_chat.py::test_history_is_passed_to_advisor  # one test

flask --app main db migrate -m "describe change"   # after changing app/models; review and commit the file
flask --app main db upgrade
flask --app main make-admin you@example.com        # --revoke to undo

.\scripts\chat.ps1           # interactive terminal chat client
.\scripts\smoke_test.ps1     # end-to-end check against a running server, incl. a real Gemini call (-BaseUrl to target Docker)
```

The dev SQLite file is at `backend/instance/dev.db` (Flask-SQLAlchemy resolves relative SQLite paths into `instance/`). The dev server auto-reloads on `.py` changes, and a syntax error during a reload kills it, so restart it after fixing one.

### Frontend

Run from `frontend/` with the backend running:

```bash
npm install
npm run dev        # http://localhost:5173; proxies /api to the backend
npm test           # vitest (jsdom); single test: npx vitest run -t "name"
npm run build      # type-checks (tsc -b, includes test files) then builds to dist/
npm run lint       # oxlint
```

The Vite dev proxy targets `http://127.0.0.1:5000`; override with `API_PROXY_TARGET`. In a production build the API base URL comes from `VITE_API_URL` (default `/api`).

### Full stack

`docker compose up --build` from the repo root serves everything on http://localhost:8080: nginx (static frontend, proxies `/api`) → gunicorn backend → Postgres + Redis. The backend reads `GEMINI_API_KEY`, `JWT_SECRET_KEY` and `SECRET_KEY` from `backend/.env`; compose overrides the database, Redis and proxy settings. `backend/docker-entrypoint.sh` runs `db upgrade`, then gunicorn with `gthread` workers.

## Architecture

- **App factory**: `app/__init__.py` `create_app()` (config chosen by `FLASK_ENV`) sets up `db`, `migrate`, `jwt`, `limiter`, CORS, the blueprints (`/api/auth`, `/api/chat`, `/api/portfolio`, `/api/admin`), `/api/health`, error handlers and the `make-admin` CLI command. `ProductionConfig.validate()` refuses to start without `JWT_SECRET_KEY` (32+ chars), `SECRET_KEY` and `DATABASE_URL`. `postgres://` URLs (Supabase) are rewritten to the psycopg 3 driver. `TRUSTED_PROXY_COUNT` > 0 enables `ProxyFix`, so rate limits and audit logs see real client IPs behind nginx or Render.
- **Schema**: Alembic via Flask-Migrate (`migrations/`). `tests/test_migrations.py` fails if models and migrations drift. `migrations/env.py` was edited to pass `disable_existing_loggers=False`, because `main.py` runs migrations in-process and the default would silence the app's loggers.
- **Data model** (`app/models/__init__.py`): User → ChatSession → Conversation → Message, and User → Portfolio (one per user, created lazily) → Holding (unique per symbol). Parent→child relationships use `cascade="all, delete-orphan"`. `AuditLog` deliberately has no relationship to User, so logs survive account deletion. The session model is `ChatSession` (table `sessions`) to avoid confusion with `db.session`.
- **Chat**: `POST /api/chat/session` creates a session plus its first conversation. Two ways to send a message: `POST /api/chat/message` returns the full reply (used by the PowerShell scripts), and `POST /api/chat/message/stream` streams Server-Sent Events (`delta`, then `done` or `error`), which the frontend uses. Both commit the user and assistant messages together, or nothing if Gemini fails. **Streaming gotcha:** a real server closes the request's DB session before the response generator runs, so `stream_message` builds the whole Gemini request in the view (`advisor.build_request`, which reads history and portfolio) and saves in a fresh session at the end. The test fakes call `close_request_session()` to reproduce this, because the Flask test client keeps the session open.
- **Advisor** (`app/services/advisor.py`): the system prompt includes holdings and live prices. History is capped at `CHAT_HISTORY_LIMIT`. Stored role `"assistant"` maps to Gemini's `"model"`. `gemini-2.5-*` counts thinking tokens against `GEMINI_MAX_OUTPUT_TOKENS`, so a low limit truncates answers; truncated replies get a visible note appended.
- **Quotes** (`app/services/quotes.py`): yfinance (Yahoo's unofficial API) with a 60s in-process cache. Unknown symbols and network failures return `None` rather than raising. `QUOTES_ENABLED=false` turns it off (off in tests).
- **Rate limiting**: Flask-Limiter. Login and register are limited per IP (`AUTH_RATE_LIMIT`). Both message endpoints share one per-user allowance (`chat_limit` in `routes/chat.py`, `CHAT_RATE_LIMIT`). Storage is `RATELIMIT_STORAGE_URI`: `memory://` in development, Redis in compose and Render, which is needed once there are several gunicorn workers.
- **Auth**: JWT subject is `str(user.id)`; use `app.middleware.current_user_id()`. Admin routes use `@admin_required`. Logins lock the account after `MAX_FAILED_LOGINS` failures; admins unlock it.
- **Frontend**: all HTTP goes through `src/api.ts` (typed `api` object, `ApiError`, `parseSSE`/`streamMessage`). The JWT lives in localStorage; `src/auth.tsx` validates it on load and logs out on any 401. `App.tsx` renders different route sets for logged-out users, users and admins (no per-route guards). Chat uses one optional-param route `/chat/:conversationId?` so the page doesn't remount when a new chat gets its ID, and it sets `activeIdRef` before navigating, because router navigation is a transition and a fast reply could otherwise be dropped. The portfolio page ignores out-of-order quote responses. Portfolio math is in `src/portfolio.ts`. Styling is Tailwind v4 (configured in `src/index.css`) plus `@tailwindcss/typography` for Gemini's markdown.

## Conventions

- Every query for a user-owned resource must filter by the JWT user, joining through parents where needed (see `_get_owned_conversation`, `_get_owned_holding`). Return 404, not 403, for other users' resources.
- Errors are JSON `{"error": "..."}` (429s too). Raise with `abort(code, description=...)` or return the JSON directly.
- Timestamps use the `utcnow()` helper in models (timezone-aware).
- Backend tests never call Gemini or Yahoo: use the `fake_advisor` / `fake_stream` fixtures. Tests use in-memory SQLite and `BCRYPT_ROUNDS=4`.
- Frontend tests stub `fetch` with `src/test/fakeServer.ts` (routes keyed by `"METHOD /path"`; unmatched requests throw).
- Files written from Python on this Windows machine get CRLF line endings; `.gitattributes` normalizes them and forces LF for `*.sh`.

## Environment variables

See `backend/.env.example`. Key ones: `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-2.5-flash`), `DATABASE_URL`, `JWT_SECRET_KEY`, `SECRET_KEY`, `CORS_ORIGINS`, `CHAT_RATE_LIMIT`, `AUTH_RATE_LIMIT`, `RATELIMIT_STORAGE_URI`, `TRUSTED_PROXY_COUNT`, `QUOTES_ENABLED`. Frontend: `VITE_API_URL` (build time).
