# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Set up environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the app (development)
python app.py
# App runs at http://localhost:5000 with debug=True; PORT env var overrides port

# Syntax check (no test suite exists)
python -m py_compile app.py

# Quick function test (e.g. scoring logic)
python -c "
from app import compute_points
match = {'actual_leg1_home': 2, 'actual_leg1_away': 0, 'actual_leg2_home': 3, 'actual_leg2_away': 1}
pred  = {'leg1_home': 2, 'leg1_away': 0, 'leg2_home': 1, 'leg2_away': 0}
print(compute_points(pred, match))  # expects {'leg1':10,'leg2':5,'qualifier':2,'total':17}
"

# Deploy to Render (branch watched by your service)
git add .
git commit -m "<clear change summary>"
git push origin master

# Production smoke test after deploy
export PROD_BASE_URL="https://<your-service>.onrender.com"
curl -i "$PROD_BASE_URL/"
curl -i "$PROD_BASE_URL/leaderboard"
curl -fsS "$PROD_BASE_URL/" | grep -qi "UCL"
curl -fsS "$PROD_BASE_URL/leaderboard" | grep -qi "leaderboard"
```

There are no tests, linting, or build steps configured.
If Render auto-deploy is disabled, deploy manually from the Render dashboard.

## Architecture

This is a minimal single-file Flask app (`app.py`) for a UCL Champions League quarterfinal prediction game among friends (max 12 users).

**Data layer:** All state is persisted to `data.json` (gitignored) via `load_data()` / `save_data()`. No database — every request reads from a module-level `lru_cache` and writes back on mutation (which calls `invalidate_cache()`). The data structure is:
```json
{
  "users": {
    "alice": {
      "email": "alice@example.com",
      "password_hash": "pbkdf2:sha256:...",
      "reset_token": null,
      "reset_expires": null,
      "preferred_lang": "en"
    }
  },
  "admin_password": "admin123",
  "matches": [{ "id": 1, "home_team": "...", "away_team": "...",
                "leg1_deadline": "2025-04-09T20:45:00",
                "leg2_deadline": "2025-04-16T20:45:00",
                "actual_leg1_home": null, "actual_leg1_away": null,
                "actual_leg2_home": null, "actual_leg2_away": null }],
  "predictions": { "alice": { "1": { "leg1_home": 2, "leg1_away": 1, ... } } }
}
```

`migrate_data(data)` runs inside `load_data()`: if `data["users"]` is a list (old format), it converts each username to a dict entry with all fields `null` and saves. It also backfills `preferred_lang: null` for any user record missing that key. Migrated users (no `password_hash`) are prompted to set an email/password on their next login.

**Critical type gotcha:** Match `id` is an `int` inside `matches[]`, but predictions are keyed by `str(match["id"])`. Always use `str(match_id)` when reading/writing `data["predictions"][username]`.

**Auth:** Username + password login. Self-registration at `/register` (username, email, password; still capped at 12). Password reset via SMTP email (`/forgot-password` → `/reset-password/<token>`; 1-hour token). Migrated users (no password_hash) are redirected to `/complete-profile` after login. Admin access is a separate password stored in `data.json`, gated by `session["is_admin"]`. The admin nav link is shown to all logged-in users but the panel requires the password.

`app.secret_key` is hardcoded in the source (`"ucl-forecast-secret-key-change-me"`). For production, override it via an env var.

**SMTP env vars (all optional; reset email silently skipped if unset):**
| Var | Default | Purpose |
|-----|---------|---------|
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port (STARTTLS) |
| `SMTP_USER` | — | SMTP login username |
| `SMTP_PASS` | — | SMTP login password |
| `SMTP_FROM` | = SMTP_USER | From address in emails |
| `APP_BASE_URL` | `http://localhost:5000` | Used to build reset links |

**Caching:** Two layers, both per-request via Flask `g`:
- `load_data_cached()` — module-level `lru_cache(maxsize=1)` wrapping `load_data()`; cleared by every `save_data()` call via `invalidate_cache()`.
- `get_cached_time()` — stores `datetime.now()` in `g.now` once per request (set in `before_request`); used by `is_leg_locked()` so the clock doesn't drift mid-request.
- `get_match_by_id()` — builds a `{id: match}` dict in `g._match_cache` on first call per request.

**Scoring (`compute_points`):**
- 10 pts — exact score for a leg
- 7 pts — correct result + correct goal difference for a leg
- 5 pts — correct result only for a leg
- 2 pts — correct qualifier (aggregate tie-winner)
- Max 22 pts per tie (10 + 10 + 2)

Aggregate qualifier logic: team A = leg1 home team. `agg_home = actual_leg1_home + actual_leg2_away`. On aggregate tie, team A advances unless team B won leg 2 outright (i.e. `a2h >= a2a` → team A advances; `a2h < a2a` → team B advances). In practice, the admin enters real results so the aggregate naturally resolves; the tiebreaker is only a code-level fallback. `get_qualifier(match)` returns the qualifying team name (used by `/bracket`); `build_leaderboard(data)` returns sorted rows of `{user, total, breakdown}`.

**Templates:** Jinja2 templates in `templates/`, all extending `base.html`. Bootstrap 5.3 dark theme with a UCL blue color scheme. No JS beyond Bootstrap bundle (no custom JS). All CSS lives inline in `base.html` `<style>` block. UCL blue palette: `#1e50a0` (primary), `#4da3ff` (accent), `#0a0e27` (body bg).

**Deadline locking (`is_leg_locked`):** Compares `get_cached_time()` against ISO-format deadline strings stored per-match. Locked legs cannot be edited by users; admin can always enter/update results.

**Admin panel (`/admin`):** Password-gated via `session["is_admin"]`. Supports: add/edit/delete matches, enter results, create users (`add_user` action — same fields as `/register`, bypasses the 12-user self-registration cap only in spirit; cap is still enforced), and remove registered users (removing a user also deletes their predictions and invalidates their session if active). All admin actions are POST with an `action` field dispatching to the relevant branch.

**Localization:** Two languages are supported: English (`en`) and Spanish (`es`), stored in `SUPPORTED_LANGS`. All user-facing strings pass through `translate(text, **kwargs)`, which looks up `SPANISH_TRANSLATIONS` when `g.lang == "es"`. The `_` shorthand is injected into every Jinja2 template via `inject_i18n_helpers`. Language resolution order (highest priority first): user's `preferred_lang` DB field → `session["lang"]` → browser `Accept-Language` header → default `"en"`. Saving a prediction at `/set-language/<lang>` also persists `preferred_lang` to the user record.

**Routes summary:**
- `/` — sign-in form (home.html)
- `/register` — new user registration
- `/complete-profile` — migrated users set email + password
- `/forgot-password` — request password reset email
- `/reset-password/<token>` — set new password via token
- `/set-language/<lang>` — switch UI language; persists to user record if logged in
- `/dashboard` — per-user predictions + mini leaderboard
- `/predict/<match_id>` — submit/edit score predictions
- `/leaderboard` — full leaderboard with per-match breakdown
- `/bracket` — aggregate results and qualifier display
- `/admin` — admin panel (match management + user management)
