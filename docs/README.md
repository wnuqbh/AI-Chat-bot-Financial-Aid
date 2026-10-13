# Documentation

**Purpose:** Index of the project documentation, and which documents to read for your role.

![Chat page answering a question about the user's portfolio](screenshots/chat-answer.png)

## Documents

| Document | What it covers | Main readers |
|---|---|---|
| [SETUP.md](SETUP.md) | Local development setup, Docker Compose, verifying it works | New developers |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System diagram, database schema, request flows | Everyone technical |
| [BACKEND.md](BACKEND.md) | Flask app structure, models, routes, services, config | Backend developers |
| [FRONTEND.md](FRONTEND.md) | React structure, routing, state, streaming, styling | Frontend developers |
| [API.md](API.md) | Every endpoint, with real request and response examples | Frontend devs, API consumers, QA |
| [SECURITY.md](SECURITY.md) | Auth, roles, rate limits, validation, audit logging | Security reviewers |
| [TESTING.md](TESTING.md) | Running the test suites, what they cover, mocking | Developers, QA |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Supabase + Render + Vercel, or one Docker host | DevOps |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common errors and how to fix them | Everyone |
| [USER_GUIDE.md](USER_GUIDE.md) | How to use the app, with screenshots | End users, support |

## Reading order by role

- **Backend developer:** SETUP → BACKEND, then ARCHITECTURE, SECURITY and API as reference.
- **Frontend developer:** SETUP → FRONTEND, then API and ARCHITECTURE.
- **DevOps:** DEPLOYMENT, then ARCHITECTURE and SETUP.
- **Security reviewer:** SECURITY → ARCHITECTURE, then BACKEND (code patterns) and TESTING (coverage).
- **End user or support:** USER_GUIDE, then TROUBLESHOOTING.

## Evidence

The screenshots in [`screenshots/`](screenshots/) were captured on 2026-10-13 from the app running locally (`python main.py` + `npm run dev`) against a throwaway database, with a real Gemini API key and live Yahoo Finance prices. The API examples in [API.md](API.md) are real responses from that same run. The test output images in [TESTING.md](TESTING.md) are the actual output of `pytest -v` and `npm test` on the same day.

## Keeping these docs accurate

- Update the relevant document in the same commit as the code change.
- Use real commands (`python main.py`, not "start the server") and real examples.
- When the UI changes visibly, retake the affected screenshots.
- Update the **Last Updated** line at the bottom of each document you change.

---
**Last Updated:** 2026-10-13
**Status:** Complete
