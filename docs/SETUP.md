# Local Setup

**Purpose:** Get the app running on your machine for development, from a fresh clone.

## Overview

You run two processes: the Flask backend on port 5000 and the Vite frontend on port 5173, which forwards `/api` calls to the backend. Alternatively, Docker Compose runs the whole production-like stack on port 8080.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Clone the repo](#clone-the-repo)
- [Backend](#backend)
- [Frontend](#frontend)
- [Verify everything works](#verify-everything-works)
- [Make yourself an admin](#make-yourself-an-admin)
- [Docker Compose](#docker-compose)
- [Common setup problems](#common-setup-problems)

## Prerequisites

| Tool | Version used | Needed for |
|---|---|---|
| Python | 3.13 | Backend |
| Node.js | 24 | Frontend |
| Git | any | Cloning |
| Docker Desktop | optional | Running the full stack |
| Gemini API key | free | Chat replies. Get one at https://aistudio.google.com/apikey |

## Clone the repo

```bash
git clone https://github.com/<you>/financial-advisor-chatbot.git
cd financial-advisor-chatbot
```

## Backend

From `backend/`:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1          # PowerShell
# source venv/Scripts/activate     # Git Bash on Windows
# source venv/bin/activate         # macOS / Linux
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and set at least:

```ini
GEMINI_API_KEY=your-key-here
```

The other values in `.env.example` are fine for development. In development `JWT_SECRET_KEY` and `SECRET_KEY` fall back to built-in dev values if left blank.

Start the server:

```bash
python main.py
```

`main.py` applies database migrations first, creating `backend/instance/dev.db` (SQLite) on the first run, then serves on http://127.0.0.1:5000. It reloads automatically when you change a `.py` file. If a reload hits a syntax error the server stops, so restart it after fixing the error.

To use a different database file, for example to keep demo data separate:

```powershell
$env:DATABASE_URL = "sqlite:///demo.db"; python main.py
```

## Frontend

In a second terminal, from `frontend/`:

```bash
npm install
npm run dev
```

Open http://localhost:5173. The dev server forwards `/api/*` to `http://127.0.0.1:5000`. To point it elsewhere, set `API_PROXY_TARGET`:

```powershell
$env:API_PROXY_TARGET = "http://127.0.0.1:8000"; npm run dev
```

You don't need a frontend `.env` in development. `VITE_API_URL` only matters for production builds (see [DEPLOYMENT.md](DEPLOYMENT.md)).

## Verify everything works

1. Health check:

   ```bash
   curl http://127.0.0.1:5000/api/health
   # {"status": "ok"}
   ```

2. Open http://localhost:5173. You should see the login page:

   ![Login page](screenshots/login.png)

3. Click **Sign up**, create an account, and ask a question. A reply should stream in.

4. Optional end-to-end check from PowerShell, including a real Gemini call:

   ```powershell
   cd backend
   .\scripts\smoke_test.ps1
   ```

5. Run the tests (see [TESTING.md](TESTING.md)):

   ```bash
   cd backend && pytest
   cd frontend && npm test
   ```

## Make yourself an admin

Register in the UI first, then from `backend/` with the venv active:

```bash
flask --app main make-admin you@example.com
# you@example.com is now an admin.
```

Log out and back in to see the **Admin** tab. Undo with `--revoke`.

## Docker Compose

Runs nginx + the built frontend, gunicorn + Flask, Postgres 17 and Redis 7, like production.

```bash
cp backend/.env.example backend/.env
# set GEMINI_API_KEY, JWT_SECRET_KEY and SECRET_KEY in backend/.env
#   python -c "import secrets; print(secrets.token_hex(32))"
docker compose up --build
```

Open http://localhost:8080. Compose sets `FLASK_ENV=production`, so the backend refuses to start without `JWT_SECRET_KEY` (32+ characters) and `SECRET_KEY`. The database, Redis and proxy settings in `docker-compose.yml` override `.env`.

Make an admin inside the container:

```bash
docker compose exec backend flask --app main make-admin you@example.com
```

To test the Docker stack with the smoke test: `.\scripts\smoke_test.ps1 -BaseUrl http://localhost:8080/api`.

## Common setup problems

| Symptom | Fix |
|---|---|
| `venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Frontend shows "Cannot reach the server. Is the backend running?" | Start `python main.py`, or check `API_PROXY_TARGET` |
| Chat replies fail with "GEMINI_API_KEY is not configured" | Set it in `backend/.env` and restart the backend |
| `Address already in use` / port 5000 taken | See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#port-already-in-use) |

More in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## See Also

- [BACKEND.md](BACKEND.md) and [FRONTEND.md](FRONTEND.md) for the codebases
- [DEPLOYMENT.md](DEPLOYMENT.md) for going live

---
**Last Updated:** 2026-10-13
**Status:** Complete
