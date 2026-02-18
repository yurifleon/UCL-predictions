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
python3 app.py
# App runs at http://localhost:5000 with debug=True
```

### Syntax Check
```bash
python3 -m py_compile app.py
```

### Linting (optional, if ruff installed)
```bash
ruff check app.py
ruff check app.py --fix  # auto-fix issues
```

### Testing (manual)
```bash
# Start app in background
python3 app.py &

# Test all routes with curl
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/           # 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/dashboard  # 302 (redirect if not logged in)

# Login and test authenticated routes
curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt -L \
  -X POST http://localhost:5000/login -d "username=testuser"

# Test dashboard after login
curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt \
  http://localhost:5000/dashboard

# Test admin (requires password)
curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt -L \
  -X POST http://localhost:5000/admin -d "password=admin123"

# Kill background app
pkill -f "python3 app.py"
```

### Running a Single Manual Test
```bash
# Quick syntax check for a specific function/feature
python3 -c "
import sys
sys.path.insert(0, '.')
from app import compute_points, load_data, save_data
# Test scoring function
match = {'id': 1, 'actual_leg1_home': 2, 'actual_leg1_away': 1, 'actual_leg2_home': 1, 'actual_leg2_away': 2}
pred = {'leg1_home': 2, 'leg1_away': 1, 'leg2_home': 0, 'leg2_away': 2}
pts = compute_points(pred, match)
print(f'Points: {pts}')
assert pts == 5  # 3 (exact leg1) + 2 (correct qualifier)
print('Test passed!')
"
```

## Code Style Guidelines

### General Principles
- Keep it simple - this is a minimal single-file app
- No external stylesheets or build steps
- All CSS inline in `templates/base.html`
- Bootstrap 5.3 dark theme with UCL blue palette (`#1e50a0`)

### Imports (Order: stdlib, third-party, local)
```python
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
- Use parentheses for line continuation

### Naming Conventions
- **Functions**: `snake_case` (e.g., `load_data`, `compute_points`)
- **Variables**: `snake_case` (e.g., `user_preds`, `match_id`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DATA_FILE`, `DEFAULT_DATA`)
- **Classes**: `PascalCase` (rare in this project)
- **Routes**: `/lowercase_with_underscores`
- **Templates**: `lowercase_with_underscores.html`
- **Route functions**: `snake_case` matching route name

### Type Hints
- Use type hints where beneficial: `def func(x: int) -> str:`
- Common types: `int`, `str`, `bool`, `Optional[type]`, `List[type]`, `Dict[key_type, value_type]`

### Error Handling
- Use try/except for parsing (e.g., `int()` conversion, `datetime.fromisoformat`)
- Catch specific exceptions: `except (ValueError, TypeError):`
- Flash messages for user feedback: `flash("message", "success"|"danger")`
- Redirect with flash for invalid state, not error pages
- Never expose stack traces to users

### Data Structures
- Match IDs stored as strings in predictions dict: `predictions[username][match_id_str]`
- Use `str(match["id"])` when accessing predictions
- All usernames stored lowercase
- Use dict lookups instead of list iterations where possible

### Database/State
- All state in `data.json`
- Load with `load_data()`, save with `save_data(data)`
- Always call `save_data()` after mutations
- Use Flask's `g` object for per-request caching (e.g., datetime, match lookups)
- Call `invalidate_cache()` after saving data if using cached loads

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
- Use `{% block content %}{% endblock %}` for page-specific content

### Performance Considerations
- Cache `datetime.now()` per request using `g` object via `get_cached_time()`
- Use dict lookup `get_match_by_id()` for match-by-ID instead of `next()` generator
- Invalidate caches in `save_data()` if implementing caching
- Use `@lru_cache` for expensive pure functions

### Security
- Never commit secrets (admin passwords, session keys) to git
- `app.secret_key` should be changed in production
- Admin routes check `session.get("is_admin")`
- Validate all user inputs (especially in admin actions)
- Use parameterized approaches for any future database queries

### Testing Guidelines
- No automated test framework configured
- Manual testing via browser/curl after changes
- Verify: login, predictions, leaderboard, admin panel
- Test edge cases: empty data, max users, deadline locking

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

### Aggregate Qualifier Logic
Team A = leg1 home team. `agg_home = actual_leg1_home + actual_leg2_away`. On aggregate tie, leg2 home side (team B) advances unless leg2 result is a draw, in which case team A advances.

## Common Tasks

### Adding a new route
1. Add `@app.route()` decorator with appropriate methods
2. Load data with `load_data()`
3. Check session auth if needed
4. Return `render_template()` or `redirect()`

### Adding a template
1. Create `templates/new_page.html`
2. Extend `base.html`
3. Add block `{% block content %}{% endblock %}`

### Modifying scoring
- Edit `compute_points()` function
- Test with known scores
- Update this AGENTS.md if scoring logic changes

### Adding a new field to matches
1. Add field to `DEFAULT_DATA` matches template
2. Update admin form in `admin.html`
3. Handle in route logic
4. Update templates if display needed
