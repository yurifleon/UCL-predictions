# AGENTS.md

Guidance for coding agents working in this repository.

## Project Snapshot
- Single-file Flask app (`app.py`) with Jinja templates.
- Domain: UCL two-leg tie prediction game.
- Persistence: `data.json` (JSON file, no DB).
- Frontend: Bootstrap 5.3 via server-rendered templates.
- Auth: username/password + profile completion + reset-token email flow.

## Agent Rule Files Present
- `.cursor/rules/`: not present.
- `.cursorrules`: not present.
- `.github/copilot-instructions.md`: not present.
- `CLAUDE.md` exists; treat it as repo-specific source of truth.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
# Default http://localhost:5000
python3 app.py

# Override port
PORT=5050 python3 app.py
```

## Build / Lint / Test Commands
No formal build pipeline or test framework is configured.

```bash
# Build-equivalent check (syntax)
python3 -m py_compile app.py

# Optional lint if installed locally
ruff check app.py
```

## Single Test Command (Important)
Use this as the canonical one-off logic test:

```bash
python3 -c "from app import compute_points; m={'actual_leg1_home':2,'actual_leg1_away':1,'actual_leg2_home':1,'actual_leg2_away':2}; p={'leg1_home':2,'leg1_away':1,'leg2_home':0,'leg2_away':2}; r=compute_points(p,m); print(r); assert r=={'leg1':3,'leg2':1,'qualifier':2,'total':6}"
```

## Smoke Test Routes
```bash
# Terminal 1
python3 app.py

# Terminal 2
curl -i http://localhost:5000/
curl -i http://localhost:5000/leaderboard
```

## Key Files
- `app.py`: routes, auth, scoring, admin actions, persistence.
- `templates/base.html`: shared layout and CSS.
- `templates/*.html`: views.
- `requirements.txt`: dependencies.
- `data.json`: runtime state (do not commit real user data).

## Architecture Constraints To Preserve
- Data is cached through `load_data_cached()` (`lru_cache(maxsize=1)`).
- Every mutation must call `save_data(data)` to persist and invalidate cache.
- `migrate_data(data)` supports old user-schema migration.
- Match IDs are `int` in `matches`, but prediction keys are `str`.
- Always use `str(match_id)` for `data["predictions"][username]` access.
- Request-scoped caches live on `flask.g` (`g.now`, `g._match_cache`).

## Current Data Shape
Top-level `data.json` keys:
- `users`
- `admin_password`
- `matches`
- `predictions`

User record keys:
- `email`
- `password_hash`
- `reset_token`
- `reset_expires`

## Code Style Guidelines

### Imports
- Order: standard library, third-party, local.
- Keep imports explicit; avoid wildcard imports.
- Follow existing module style in touched file.

### Formatting
- 4-space indentation, PEP 8 conventions.
- Keep line length readable (target <= 100-120 chars).
- Two blank lines between top-level defs.
- Prefer f-strings over `%` or `.format()`.

### Naming
- Functions/variables: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Template filenames: lowercase with underscores.
- Route handlers: descriptive `snake_case` names.

### Types
- Codebase is mostly untyped today.
- Add type hints only when they improve clarity in touched code.
- If adding hints, use modern built-in generics (`dict[str, int]`).
- Avoid partial noisy annotations with little value.

### Error Handling
- Validate/normalize input close to the boundary (`strip`, lowercase, `int(...)`).
- Catch specific expected exceptions (`ValueError`, `TypeError`, `KeyError`).
- Use `flash(..., "danger"|"warning"|"success"|"info")` for user feedback.
- Prefer redirect/render recovery over hard failures for user mistakes.
- Do not expose internals or secrets in messages.

### Flask and Route Patterns
- Gate private pages with `session.get("username")` checks early.
- Gate incomplete migrated users with `user_profile_complete(...)`.
- Keep route logic straightforward; extract helpers for reusable logic.
- Keep business rules in Python helpers, not templates.

### Data and State Changes
- Preserve backward compatibility of stored JSON shape unless requested.
- On schema change, include migration logic near `migrate_data`.
- When deleting match/user entities, clean related prediction data.
- Do not bypass `save_data`; direct file writes are not acceptable.

### Scoring Rules
- Keep `compute_points` and `get_qualifier` behavior consistent unless asked.
- If scoring changes, verify dashboard + leaderboard + bracket paths.

### Security Basics
- Never commit credentials, secrets, or populated personal data.
- Keep password handling on Werkzeug hash helpers only.
- Keep reset tokens random, expiring, and single-use.
- Treat `app.secret_key` and `admin_password` defaults as dev-only.

## Common Gotchas
- `matches` uses integer IDs, but prediction maps use string IDs; convert with `str(match_id)`.
- Updating in-memory `data` without calling `save_data(data)` will silently drop changes.
- Editing users/matches without related cleanup can leave orphaned prediction entries.
- Touching legacy-schema assumptions can break migrated users; preserve `migrate_data(data)` behavior.
- Broad exception handlers in request logic can hide user-facing errors; keep catches explicit.
- Changing scoring helpers requires validating dashboard, leaderboard, and bracket consistency.

## Agent Workflow
1. Read affected helper/route/template fully before editing.
2. Make minimal edits consistent with current patterns.
3. Run `python3 -m py_compile app.py` after Python changes.
4. Run the single-test command for logic touched.
5. Smoke-test impacted routes manually when behavior changes.

## Pre-Completion Checklist
- App boots locally with `python3 app.py`.
- Syntax check passes.
- Relevant single-test/logic check passes.
- No secrets or runtime `data.json` changes accidentally staged.
