# Advisor: AI financial education chatbot

A full-stack app where retail investors chat with an AI advisor (Google Gemini) that knows their portfolio and current market prices.

- **Chat:** answers stream in word by word, conversations are saved, and replies are rendered as markdown
- **Portfolio:** holdings with live prices, market value, gain/loss and weights
- **Accounts:** sign-up and login (JWT), lockout after repeated failed logins, rate limiting
- **Admin:** user list with account unlock, and a filterable audit log

Stack: Flask, SQLAlchemy and Alembic, with Postgres in production (SQLite in development) and Redis for rate limits · React 19, TypeScript, Vite and Tailwind · Docker Compose.

## Run it with Docker

```bash
cp backend/.env.example backend/.env
# edit backend/.env: set GEMINI_API_KEY, JWT_SECRET_KEY and SECRET_KEY
docker compose up --build
```

Open http://localhost:8080.

## Run it for development

Backend (from `backend/`):

```bash
python -m venv venv
venv\Scripts\activate            # Windows; on macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # set GEMINI_API_KEY
python main.py                    # http://127.0.0.1:5000, applies migrations on start
```

Frontend (from `frontend/`, in a second terminal):

```bash
npm install
npm run dev                       # http://localhost:5173
```

Tests: `pytest` in `backend/`, and `npm test` in `frontend/`.

## Documentation

Full documentation, with screenshots, is in [docs/](docs/README.md): setup, architecture, backend, frontend, API reference, security, testing, deployment, troubleshooting and a user guide.

## Deploy

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): Supabase (database) + Render (API) + Vercel (frontend), or a single Docker host.

---

For education only. This app is not financial advice.
