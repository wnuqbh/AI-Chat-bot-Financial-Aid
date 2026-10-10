# Deploying

The production setup is three free-tier services:

| Part | Host | Config in this repo |
|---|---|---|
| Database (Postgres) | [Supabase](https://supabase.com) | none, just a connection string |
| Backend API + Redis | [Render](https://render.com) | `render.yaml` |
| Frontend | [Vercel](https://vercel.com) | `frontend/vercel.json` |

Do them in this order, because each step needs a URL from the one before.

Alternatively, run everything on any server with Docker using `docker compose up -d --build` (see the end of this guide).

## 0. Push the code to GitHub

Render and Vercel deploy from a GitHub repository.

```bash
git remote add origin https://github.com/<you>/financial-advisor-chatbot.git
git push -u origin main
```

The `CI` workflow (`.github/workflows/ci.yml`) then runs the backend tests, frontend lint/tests/build and both Docker builds on every push.

## 1. Database: Supabase

1. Create a project and save the database password you choose.
2. Click **Connect** at the top of the project page, then copy the **Session pooler** connection string. Render can't reach Supabase's direct connection, which is IPv6-only. It looks like:
   `postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`
3. Replace `[YOUR-PASSWORD]` with your password and add `?sslmode=require` to the end.

You don't need to create any tables. The backend runs its migrations every time it starts.

## 2. Backend: Render

1. Render dashboard → **New → Blueprint** → choose the repository. Render reads `render.yaml` and proposes the `advisor-api` web service and the `advisor-ratelimit` Redis.
2. Fill in the values it asks for:
   - `DATABASE_URL`: the Supabase string from step 1
   - `GEMINI_API_KEY`: from https://aistudio.google.com/apikey (consider a separate key from your development one)
   - `CORS_ORIGINS`: leave as `https://example.com` for now and fix it in step 4
   
   `JWT_SECRET_KEY` and `SECRET_KEY` are generated for you.
3. Deploy. When it's live, open `https://advisor-api-XXXX.onrender.com/api/health` and check that it returns `{"status": "ok"}`.

Free Render services sleep after 15 minutes without traffic, so the first request afterwards takes about a minute.

## 3. Frontend: Vercel

1. Vercel dashboard → **Add New → Project** → import the repository.
2. Set **Root Directory** to `frontend`. Vercel detects Vite and fills in the build settings.
3. Add the environment variable `VITE_API_URL` = `https://advisor-api-XXXX.onrender.com/api` (your Render URL plus `/api`).
4. Deploy and note the URL, e.g. `https://advisor-abc.vercel.app`.

`VITE_API_URL` is baked in when the site is built. If you change it, redeploy.

## 4. Connect them

In Render → `advisor-api` → **Environment**, set `CORS_ORIGINS` to your exact Vercel URL, with no trailing slash. You can list several, separated by commas. Save; Render redeploys.

Then open the Vercel URL, sign up, add a holding and ask a question.

## 5. Make yourself an admin

Sign up on the live site first. Render's free plan has no Shell, so run the command from your own machine against the production database (from `backend/`, venv active). In PowerShell:

```powershell
$env:DATABASE_URL = "<your Supabase connection string>"
flask --app main make-admin you@example.com
Remove-Item Env:DATABASE_URL
```

On a paid Render plan you can instead run `flask --app main make-admin you@example.com` in **advisor-api → Shell**. Log out and back in to see the **Admin** tab.

## Operating notes

- **Schema changes:** after changing `app/models`, run `flask --app main db migrate -m "describe change"` locally, review the generated file in `backend/migrations/versions/`, and commit it. Deploys apply it automatically.
- **Rate limits:** adjust `CHAT_RATE_LIMIT` / `AUTH_RATE_LIMIT` in Render's environment (e.g. `20 per minute;500 per day`).
- **Live prices** come from Yahoo Finance's unofficial API, which is fine for personal use. For a commercial product, replace `_fetch_quote` in `backend/app/services/quotes.py` with a licensed data provider, or set `QUOTES_ENABLED=false`.
- **Secrets** live only in the hosts' environment settings, never in git. To revoke every login at once, change `JWT_SECRET_KEY`.

## Alternative: one server with Docker Compose

On any Linux server with Docker:

```bash
git clone <repo> && cd financial-advisor-chatbot
cp backend/.env.example backend/.env   # set GEMINI_API_KEY, JWT_SECRET_KEY, SECRET_KEY
docker compose up -d --build
```

The app is served on port 8080. The bundled Postgres stores its data in the `pgdata` Docker volume; back it up. For HTTPS, put a reverse proxy such as Caddy in front, and set `TRUSTED_PROXY_COUNT=2` in `docker-compose.yml`, since there are then two proxies in front of the backend. Also change the Postgres password in `docker-compose.yml`.
