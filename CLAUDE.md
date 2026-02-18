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
# App runs at http://localhost:5000 with debug=True
```

There are no tests, linting, or build steps configured.

## Architecture

This is a minimal single-file Flask app (`app.py`) for a UCL Champions League quarterfinal prediction game among friends (max 12 users).

**Data layer:** All state is persisted to `data.json` (gitignored) via `load_data()` / `save_data()`. No database — every request reads the file and writes it back on mutation. The data structure is:
```json
{
  "users": ["alice", "bob"],
  "admin_password": "admin123",
  "matches": [{ "id": 1, "home_team": "...", "away_team": "...",
                "leg1_deadline": "2025-04-09T20:45:00",
                "leg2_deadline": "2025-04-16T20:45:00",
                "actual_leg1_home": null, "actual_leg1_away": null,
                "actual_leg2_home": null, "actual_leg2_away": null }],
  "predictions": { "alice": { "1": { "leg1_home": 2, "leg1_away": 1, ... } } }
}
```

**Auth:** Username-only login (case-insensitive, stored lowercase) creates the account on first use. Admin access is a separate password stored in `data.json`, gated by `session["is_admin"]`.

**Scoring (`compute_points`):**
- 3 pts — exact score for a leg
- 1 pt — correct outcome (win/draw) for a leg
- 2 pts — correct qualifier (aggregate tie-winner)
- Max 8 pts per tie (two legs + qualifier)

Aggregate qualifier logic: team A = leg1 home team. `agg_home = actual_leg1_home + actual_leg2_away`. On aggregate tie, the leg2 home side (team B) advances unless leg2 result is a draw, in which case team A advances.

**Templates:** Jinja2 templates in `templates/`, all extending `base.html`. Bootstrap 5.3 dark theme with a UCL blue color scheme. No JS beyond Bootstrap bundle (no custom JS).

**Deadline locking (`is_leg_locked`):** Compares `datetime.now()` against ISO-format deadline strings stored per-match. Locked legs cannot be edited by users; admin can always enter/update results.

**Admin panel (`/admin`):** Password-gated via `session["is_admin"]`. Supports: add/edit/delete matches, enter results, and remove registered users (removing a user also deletes their predictions and invalidates their session if active).

**Routes summary:**
- `/` — login/user selection (home.html)
- `/dashboard` — per-user predictions + mini leaderboard
- `/predict/<match_id>` — submit/edit score predictions
- `/leaderboard` — full leaderboard with per-match breakdown
- `/bracket` — aggregate results and qualifier display
- `/admin` — admin panel (match management + user management)

**Styling:** All CSS lives inline in `base.html` `<style>` block. No external stylesheet or build step. UCL blue palette: `#1e50a0` (primary), `#4da3ff` (accent), `#0a0e27` (body bg).
