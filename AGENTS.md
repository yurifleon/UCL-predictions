# AGENTS.md - UCL Forecast Development Guide

This file provides guidance for agentic coding agents working on this codebase.

## Project Overview

- **Project**: UCL Champions League Quarterfinal Prediction Game
- **Type**: Single-file Flask webapp
- **Tech Stack**: Python 3.12+, Flask, Jinja2 templates, Bootstrap 5.3
- **Data**: JSON file persistence (`data.json`)

## Commands

### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Running
```bash
python app.py
# App runs at http://localhost:5000 with debug=True
```

### Syntax Check
```bash
python3 -m py_compile app.py
```

### Testing (manual)
- Start app: `python3 app.py`
- Test routes with curl or browser:
  - `GET /` - Home/login page
  - `POST /login` - Login with username param
  - `GET /dashboard` - User predictions
  - `GET /leaderboard` - Full leaderboard
  - `GET /bracket` - Aggregate results
  - `GET /admin` - Admin panel

## Code Style Guidelines

### General Principles
- Keep it simple - this is a minimal single-file app
- No external stylesheets or build steps
- All CSS inline in `templates/base.html`
- Bootstrap 5.3 dark theme with UCL blue palette (`#1e50a0`)

### Imports
```python
# Standard library first, then third-party
import json
import os
from datetime import datetime
from functools import lru_cache

from flask import Flask, render_template, request, redirect, url_for, session, flash, g
```

### Formatting
- 4-space indentation (PEP 8)
- Maximum line length: 120 characters
- Blank lines: 2 between top-level definitions, 1 between functions
- Use f-strings for string formatting

### Naming Conventions
- **Functions**: `snake_case` (e.g., `load_data`, `compute_points`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DATA_FILE`, `DEFAULT_DATA`)
- **Routes**: `/lowercase_with_underscores`
- **Templates**: `lowercase_with_underscores.html`

### Data Structures
- Match IDs stored as strings in predictions dict: `predictions[username][match_id_str]`
- Use `str(match["id"])` when accessing predictions
- All usernames stored lowercase

### Error Handling
- Use try/except for parsing (e.g., `int()` conversion, `datetime.fromisoformat`)
- Flash messages for user feedback: `flash("message", "success"|"danger")`
- Redirect with flash for invalid state, not error pages

### Database/State
- All state in `data.json`
- Load with `load_data()`, save with `save_data(data)`
- Always call `save_data()` after mutations
- Use Flask's `g` object for per-request caching (e.g., datetime, match lookups)

### Routes Pattern
```python
@app.route("/route_name", methods=["GET", "POST"])
def route_name():
    username = session.get("username")
    if not username:
        return redirect(url_for("home"))
    
    data = load_data()
    # ... logic ...
    return render_template("template.html", var=value)
```

### Templates
- All templates in `templates/` directory
- Extend `base.html` for consistent layout
- Use Bootstrap 5.3 classes for styling
- Pass computed data to templates (don't compute in templates)

### Performance Considerations
- Cache `datetime.now()` per request using `g` object
- Use dict lookup for match-by-ID instead of `next()` generator
- Invalidate caches in `save_data()` if implementing caching

### Security
- Never commit secrets (admin passwords, session keys)
- `app.secret_key` should be changed in production
- Admin routes check `session.get("is_admin")`

### Testing Guidelines
- No automated test framework configured
- Manual testing via browser/curl after changes
- Verify: login, predictions, leaderboard, admin panel

## Architecture Notes

### Data Schema
```json
{
  "users": ["alice", "bob"],
  "admin_password": "admin123",
  "matches": [{ "id": 1, "home_team": "...", "away_team": "...", 
                "leg1_deadline": "ISO8601", "leg2_deadline": "ISO8601",
                "actual_leg1_home": null, "actual_leg1_away": null,
                "actual_leg2_home": null, "actual_leg2_away": null }],
  "predictions": { "alice": { "1": { "leg1_home": 2, "leg1_away": 1, ... } } }
}
```

### Scoring System
- 3 pts — exact score for a leg
- 1 pt — correct outcome (win/draw) for a leg  
- 2 pts — correct qualifier (aggregate tie-winner)
- Max 8 pts per tie

### Deadline Locking
- Uses `datetime.now()` vs ISO deadline strings
- Locked legs cannot be edited by users
- Admin can always enter/update results

## Common Tasks

### Adding a new route
1. Add `@app.route()` decorator
2. Load data with `load_data()`
3. Check session auth if needed
4. Return `render_template()` or `redirect()`

### Adding a template
1. Create `templates/new_page.html`
2. Extend `base.html`
3. Add block `{% block content %}{% endblock %}`

### Modifying scoring
- Edit `compute_points()` function
- Update this AGENTS.md if scoring logic changes
