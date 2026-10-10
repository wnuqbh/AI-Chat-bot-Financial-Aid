# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Financial Advisor AI Chatbot

Full-stack conversational app where retail investors get financial guidance from an LLM (Google Gemini), with answers informed by the holdings they enter.

**Status (Oct 2026):** Flask backend (`backend/`) and React frontend (`frontend/`) both working end to end. Not yet deployed.

## Commands

### Backend

All backend commands run from `backend/` with the venv active (`venv\Scripts\Activate.ps1` in PowerShell, `source venv/Scripts/activate` in Git Bash on this machine).

```bash
pip install -r requirements.txt
cp .env.example .env          # then set GEMINI_API_KEY
python main.py                # dev server on http://127.0.0.1:5000

pytest                                                      # all tests
pytest tests/test_chat.py                                   # one file
pytest tests/test_chat.py::test_history_is_passed_to_advisor  # one test

.\scripts\chat.ps1           # interactive terminal chat client
.\scripts\smoke_test.ps1     # end-to-end check against the running server, incl. a real Gemini call (PowerShell)

docker compose up --build     # gunicorn + local Postgres, FLASK_ENV=production
```

Tables are created by `db.create_all()` in `main.py`; there are no migrations, so schema changes on an existing database mean deleting it. The dev SQLite file is at `backend/instance/dev.db` (Flask-SQLAlchemy resolves relative SQLite paths into `instance/`).

The dev server auto-reloads on `.py` changes, and a syntax error during a reload kills it, so restart it after fixing one.

### Frontend

Run from `frontend/` with the backend running:

```bash
npm install
npm run dev        # http://localhost:5173; proxies /api to the backend
npm run build      # type-checks (tsc -b) then builds to dist/
npm run lint       # oxlint
```

The Vite dev proxy targets `http://127.0.0.1:5000`; override with the `API_PROXY_TARGET` env var. In a production build the API base URL comes from `VITE_API_URL` (default `/api`). There are no frontend tests.

## Architecture

- **App factory**: `app/__init__.py` `create_app(config_name)` sets up `db`, `jwt`, CORS, the four blueprints (`/api/auth`, `/api/chat`, `/api/portfolio`, `/api/admin`), `/api/health` and all error handlers. `config.py` defines Development/Production/Testing; `ProductionConfig.validate()` refuses to start without `JWT_SECRET_KEY`, `SECRET_KEY` and `DATABASE_URL`. `postgres://` URLs (Supabase) are rewritten to use the psycopg 3 driver.
- **Data model** (`app/models/__init__.py`): User → ChatSession → Conversation → Message, and User → Portfolio (one per user, created lazily) → Holding (unique per symbol). Parent→child relationships use `cascade="all, delete-orphan"`. `AuditLog` deliberately has no relationship to User, so logs survive account deletion. The session model is `ChatSession` (table `sessions`) to avoid confusion with `db.session`.
- **Chat flow**: `POST /api/chat/session` creates a session plus its first conversation and returns `conversation_id`. `POST /api/chat/message` adds the user message, calls `app/services/advisor.py:generate_reply()` with the conversation history (last `CHAT_HISTORY_LIMIT` messages) and the user's portfolio, then commits both messages together. If Gemini fails, it rolls back and returns 503, so nothing partial is stored. Messages are stored with role `"assistant"`; the advisor maps that to Gemini's `"model"` role.
- **Validation**: request bodies go through Marshmallow schemas in `app/schemas/`. A global `ValidationError` handler turns failures into 400 `{"error", "details"}`.
- **Auth**: JWT subject is `str(user.id)`; use `app.middleware.current_user_id()` to get it back as an int. Admin routes use `@admin_required` (checks `User.is_admin`; there is no endpoint to grant admin, so set it in the database). Logins lock the account after `MAX_FAILED_LOGINS` failures; `POST /api/admin/users/<id>/unlock` clears it.
- **Audit**: `app/services/audit.py:record_audit()` adds an entry to the current transaction; the caller commits.
- **Gemini output limit**: `gemini-2.5-*` models count thinking tokens against `GEMINI_MAX_OUTPUT_TOKENS`, so a low limit truncates answers. Truncated replies get a visible "cut off" note appended.
- **Frontend**: all HTTP goes through `src/api.ts` (typed `api` object, `ApiError`). The JWT lives in localStorage; `src/auth.tsx` (`AuthProvider`/`useAuth`) validates it on load via `/auth/me` and logs out on any 401. `App.tsx` renders entirely different route sets for logged-in and logged-out users, so there's no per-route guard. Chat uses a single optional-param route `/chat/:conversationId?` so the page doesn't remount when a new chat gets its id. A session is only created when its first message is sent, and the backend titles untitled sessions from that first message. Styling is Tailwind v4 (configured in `src/index.css`, no tailwind.config) plus `@tailwindcss/typography` for rendering Gemini's markdown.

## Conventions

- Every query for a user-owned resource must filter by the JWT user, joining through parents where needed (see `_get_owned_conversation` in `routes/chat.py`, `_get_owned_holding` in `routes/portfolio.py`). Return 404, not 403, for other users' resources.
- Errors are JSON `{"error": "..."}`. Raise with `abort(code, description=...)` or return the JSON directly; the global handlers format HTTP exceptions and JWT failures.
- Timestamps use the `utcnow()` helper in models (timezone-aware; `datetime.utcnow` is deprecated).
- Tests never call Gemini: the `fake_advisor` fixture in `tests/conftest.py` monkeypatches `app.routes.chat.generate_reply`. Tests use in-memory SQLite and `BCRYPT_ROUNDS=4`.

## Environment variables

See `backend/.env.example`. Key ones: `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-2.5-flash`), `DATABASE_URL`, `JWT_SECRET_KEY`, `SECRET_KEY`, `CORS_ORIGINS` (default is the Vite dev server, `http://localhost:5173`).

## Roadmap

- **Remaining:** deploy the frontend (Vercel) and backend (Supabase Postgres), rate limiting, streaming responses, live market prices for holdings.
