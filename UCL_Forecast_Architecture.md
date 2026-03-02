# UCL Forecast — Application Architecture Overview

**Audience:** Technology Executives
**Last updated:** March 2026

---

## What the Application Does

UCL Forecast is a private prediction game for a closed group of friends (up to 12 participants) built around the UEFA Champions League 2025-26 Round of 16. Users predict scorelines for each two-legged tie across all 8 Round of 16 matches; points are awarded for exact scores, correct goal differences, and correct match outcomes. A live leaderboard ranks all participants throughout the round. The bracket view tracks progression from the Round of 16 through the Quarter-finals, Semi-finals, and Final.

---

## Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.12 | Widely supported, rapid development |
| Web framework | Flask (micro-framework) | Minimal overhead for a small, closed app |
| WSGI server | Gunicorn | Production-grade serving; replaces Flask dev server on Render |
| Frontend | Bootstrap 5.3 (dark theme) | No custom JavaScript; zero client-side build tooling |
| Data storage | JSON flat file (`data.json`) | No database infrastructure needed for ≤12 users |
| Hosting | Render (PaaS) | Zero-ops deployment via git push |
| Email | SMTP (Gmail or equivalent) | Password-reset only; optional feature |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                    Render (Cloud PaaS)               │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │              Flask Application               │   │
│  │                  (app.py)                    │   │
│  │                                              │   │
│  │  ┌────────────┐      ┌─────────────────┐    │   │
│  │  │   Routes   │─────▶│  Business Logic  │    │   │
│  │  │ (12 URLs)  │      │ Scoring, Auth,  │    │   │
│  │  └────────────┘      │  Leaderboard    │    │   │
│  │         │            └────────┬────────┘    │   │
│  │         ▼                     │             │   │
│  │  ┌────────────┐               ▼             │   │
│  │  │  Jinja2    │      ┌─────────────────┐    │   │
│  │  │ Templates  │      │   data.json     │    │   │
│  │  └────────────┘      │ (flat-file DB)  │    │   │
│  └──────────────────────└─────────────────┘────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘
         ▲                          ▲
         │ HTTPS                    │ SMTP (optional)
         │                          │
      Users                   Gmail / SMTP relay
   (≤ 12 people)             (password reset only)
```

---

## Key Architectural Decisions

### Single-File Design
The entire application — routing, business logic, data access, authentication, and email — lives in one Python file (`app.py`, ~970 lines). This is an intentional trade-off: for a private app with 12 users and a single developer, the simplicity of one file outweighs the maintainability benefits of a layered architecture.

### Flat-File Data Storage
All application state (users, predictions, match results) is persisted to a single JSON file (`data.json`). There is no database. This eliminates infrastructure complexity and operational overhead entirely. The file path is configurable via the `DATA_DIR` environment variable, which should point to a Render persistent disk (e.g. `/data`) so that user registrations and results survive new code deployments. Without a persistent disk, the free tier wipes the file on each deploy — match configurations are recovered automatically from hardcoded seed data, but user accounts would be lost.

### No Client-Side JavaScript
The UI is rendered entirely server-side using HTML templates. Bootstrap provides layout and styling; no custom JavaScript exists. This minimises attack surface, eliminates frontend build tooling, and makes the codebase trivially auditable.

### Per-Request Caching
To avoid reading `data.json` on every database call within a single HTTP request, a lightweight in-memory cache is applied at the module level. The cache is invalidated automatically on every write. This gives read performance close to an in-memory store while keeping the storage layer simple.

---

## Security Model

| Concern | Approach |
|---|---|
| User passwords | Hashed using PBKDF2-SHA256 (via Werkzeug) — never stored in plaintext |
| Admin access | Separate password-gated session; can be set via environment variable (`ADMIN_PASSWORD`) without touching code |
| Password reset | Time-limited token (1 hour) delivered by email; token is single-use |
| Open redirect protection | All redirect targets are validated to be same-origin |
| Session security | Server-side Flask sessions; secret key should be set via environment variable in production |
| User cap | Hard-coded maximum of 12 registered users; no public sign-up beyond this limit |

**Notable limitation:** `data.json` is stored on disk. Without a Render persistent disk, it is wiped on each new deployment (free tier behaviour). With a persistent disk (`DATA_DIR=/data`), data survives deployments but there is still no automated backup — periodic manual copies of `data.json` are recommended.

---

## Deployment Model

The application is hosted on **Render**, a Platform-as-a-Service (PaaS) provider. Deployment is triggered automatically by pushing to the `master` branch on GitHub. Render builds the Python environment, installs dependencies from `requirements.txt`, and starts the Flask server.

```
Developer laptop
      │
      │  git push origin master
      ▼
  GitHub (master branch)
      │
      │  Render auto-deploy webhook
      ▼
  Render (live app)
```

Configuration is managed through Render's environment variable settings, keeping secrets out of the codebase. The production start command is `gunicorn app:app --bind 0.0.0.0:$PORT` (not the Flask dev server). A persistent disk mounted at `/data` with `DATA_DIR=/data` ensures user data survives deployments.

---

## Internationalisation

The application supports **English and Spanish**. Language is selected automatically based on:
1. The user's saved preference (stored in their profile)
2. Their browser's `Accept-Language` header as a fallback

All user-facing strings are routed through a translation layer. Adding a new language requires only adding a new dictionary of translated strings in `app.py`.

---

## Scalability and Limitations

| Dimension | Current limit | Why |
|---|---|---|
| Concurrent users | ~10–20 | Single-process server; no connection pooling needed |
| Registered users | 12 (hard cap) | Business requirement; enforced in code |
| Data durability | Local disk only | No database replication or backups |
| High availability | Single instance | No load balancing; Render free-tier restarts on inactivity |
| Tournament scope | Round of 16 predictions | Scoring covers R16 only; bracket view shows R16 → QF → SF → Final |

This architecture is deliberately scoped to its purpose. It is not designed for growth beyond the current use case.

---

## Operational Runbook (Summary)

| Task | How |
|---|---|
| Change admin password | Set `ADMIN_PASSWORD` env var in Render dashboard |
| Persist user data across deploys | Add Render persistent disk at `/data`; set `DATA_DIR=/data` env var |
| Enable password-reset emails | Set `SMTP_USER`, `SMTP_PASS`, `APP_BASE_URL` env vars |
| Add/edit matches or results | Log in to `/admin` with the admin password |
| Deploy a code change | `git push origin master` (Render auto-deploys) |
| Switch to production WSGI server | Set Render start command to `gunicorn app:app --bind 0.0.0.0:$PORT` |
| Back up data | Manually copy `data.json` from the persistent disk via Render shell |
