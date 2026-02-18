import json
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = "ucl-forecast-secret-key-change-me"

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

DEFAULT_DATA = {
    "users": [],
    "admin_password": "admin123",
    "matches": [],
    "predictions": {},
}


def load_data():
    if not os.path.exists(DATA_FILE):
        save_data(DEFAULT_DATA)
        return DEFAULT_DATA.copy()
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def compute_points(prediction, match):
    """Compute points for a single tie prediction."""
    points = {"leg1": 0, "leg2": 0, "qualifier": 0, "total": 0}

    if not prediction:
        return points

    # Check leg 1
    a1h = match.get("actual_leg1_home")
    a1a = match.get("actual_leg1_away")
    if a1h is not None and a1a is not None:
        p1h = prediction.get("leg1_home")
        p1a = prediction.get("leg1_away")
        if p1h is not None and p1a is not None:
            if p1h == a1h and p1a == a1a:
                points["leg1"] = 3
            else:
                # Check correct outcome (win/draw)
                actual_outcome = (a1h > a1a) - (a1h < a1a)
                pred_outcome = (p1h > p1a) - (p1h < p1a)
                if actual_outcome == pred_outcome:
                    points["leg1"] = 1

    # Check leg 2
    a2h = match.get("actual_leg2_home")
    a2a = match.get("actual_leg2_away")
    if a2h is not None and a2a is not None:
        p2h = prediction.get("leg2_home")
        p2a = prediction.get("leg2_away")
        if p2h is not None and p2a is not None:
            if p2h == a2h and p2a == a2a:
                points["leg2"] = 3
            else:
                actual_outcome = (a2h > a2a) - (a2h < a2a)
                pred_outcome = (p2h > p2a) - (p2h < p2a)
                if actual_outcome == pred_outcome:
                    points["leg2"] = 1

    # Check qualifier (need both legs actual results)
    if all(v is not None for v in [a1h, a1a, a2h, a2a]):
        p1h = prediction.get("leg1_home")
        p1a = prediction.get("leg1_away")
        p2h = prediction.get("leg2_home")
        p2a = prediction.get("leg2_away")
        if all(v is not None for v in [p1h, p1a, p2h, p2a]):
            # Aggregate: home team in leg1 is "team A"
            actual_agg_home = a1h + a2a  # team A goals across both legs
            actual_agg_away = a1a + a2h  # team B goals across both legs
            pred_agg_home = p1h + p2a
            pred_agg_away = p1a + p2h

            if actual_agg_home != actual_agg_away:
                actual_qualifier = "home" if actual_agg_home > actual_agg_away else "away"
            else:
                # Tie on aggregate — away goals rule removed in modern UCL,
                # but we need a tiebreaker. Use home team of leg2 as qualifier
                # (simplified: admin enters result that reflects the actual qualifier)
                actual_qualifier = "home" if a2h >= a2a else "away"

            if pred_agg_home != pred_agg_away:
                pred_qualifier = "home" if pred_agg_home > pred_agg_away else "away"
            else:
                pred_qualifier = "home" if p2h >= p2a else "away"

            if actual_qualifier == pred_qualifier:
                points["qualifier"] = 2

    points["total"] = points["leg1"] + points["leg2"] + points["qualifier"]
    return points


def get_qualifier(match):
    """Return the qualifying team name or None."""
    a1h = match.get("actual_leg1_home")
    a1a = match.get("actual_leg1_away")
    a2h = match.get("actual_leg2_home")
    a2a = match.get("actual_leg2_away")
    if any(v is None for v in [a1h, a1a, a2h, a2a]):
        return None
    agg_home = a1h + a2a
    agg_away = a1a + a2h
    if agg_home > agg_away:
        return match["home_team"]
    elif agg_away > agg_home:
        return match["away_team"]
    else:
        # Tied on aggregate — leg2 home win or draw means away team (leg2 host) advances
        if a2h >= a2a:
            return match["home_team"]
        else:
            return match["away_team"]


def build_leaderboard(data):
    rows = []
    for user in data["users"]:
        user_preds = data["predictions"].get(user, {})
        total = 0
        breakdown = []
        for match in data["matches"]:
            mid = str(match["id"])
            pred = user_preds.get(mid)
            pts = compute_points(pred, match)
            breakdown.append({"match": match, "points": pts})
            total += pts["total"]
        rows.append({"user": user, "total": total, "breakdown": breakdown})
    rows.sort(key=lambda r: r["total"], reverse=True)
    return rows


def is_leg_locked(match, leg):
    """Check if a specific leg's deadline has passed."""
    key = f"leg{leg}_deadline"
    deadline_str = match.get(key)
    if not deadline_str:
        return False
    try:
        deadline = datetime.fromisoformat(deadline_str)
        return datetime.now() >= deadline
    except (ValueError, TypeError):
        return False


@app.route("/")
def home():
    if session.get("username"):
        return redirect(url_for("dashboard"))
    data = load_data()
    return render_template("home.html", users=data["users"])


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip().lower()
    if not username:
        flash("Please enter a username.", "danger")
        return redirect(url_for("home"))

    data = load_data()
    if username not in data["users"]:
        if len(data["users"]) >= 12:
            flash("Maximum 12 users reached. Pick an existing username.", "danger")
            return redirect(url_for("home"))
        data["users"].append(username)
        data["predictions"][username] = {}
        save_data(data)

    session["username"] = username
    flash(f"Welcome, {username}!", "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("is_admin", None)
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
    username = session.get("username")
    if not username:
        return redirect(url_for("home"))
    data = load_data()
    user_preds = data["predictions"].get(username, {})
    matches_info = []
    for match in data["matches"]:
        mid = str(match["id"])
        pred = user_preds.get(mid)
        pts = compute_points(pred, match)
        leg1_locked = is_leg_locked(match, 1)
        leg2_locked = is_leg_locked(match, 2)
        matches_info.append({
            "match": match,
            "prediction": pred,
            "points": pts,
            "leg1_locked": leg1_locked,
            "leg2_locked": leg2_locked,
            "fully_locked": leg1_locked and leg2_locked,
        })
    leaderboard = build_leaderboard(data)
    return render_template("dashboard.html", username=username, matches_info=matches_info, leaderboard=leaderboard)


@app.route("/predict/<int:match_id>", methods=["GET", "POST"])
def predict(match_id):
    username = session.get("username")
    if not username:
        return redirect(url_for("home"))

    data = load_data()
    match = next((m for m in data["matches"] if m["id"] == match_id), None)
    if not match:
        flash("Match not found.", "danger")
        return redirect(url_for("dashboard"))

    mid = str(match_id)
    leg1_locked = is_leg_locked(match, 1)
    leg2_locked = is_leg_locked(match, 2)

    if request.method == "POST":
        if username not in data["predictions"]:
            data["predictions"][username] = {}
        if mid not in data["predictions"][username]:
            data["predictions"][username][mid] = {}

        pred = data["predictions"][username][mid]

        if not leg1_locked:
            try:
                pred["leg1_home"] = int(request.form["leg1_home"])
                pred["leg1_away"] = int(request.form["leg1_away"])
            except (KeyError, ValueError):
                pass

        if not leg2_locked:
            try:
                pred["leg2_home"] = int(request.form["leg2_home"])
                pred["leg2_away"] = int(request.form["leg2_away"])
            except (KeyError, ValueError):
                pass

        save_data(data)
        flash("Prediction saved!", "success")
        return redirect(url_for("dashboard"))

    prediction = data["predictions"].get(username, {}).get(mid)
    return render_template(
        "predict.html",
        match=match,
        prediction=prediction,
        leg1_locked=leg1_locked,
        leg2_locked=leg2_locked,
    )


@app.route("/leaderboard")
def leaderboard():
    data = load_data()
    rows = build_leaderboard(data)
    return render_template("leaderboard.html", rows=rows, matches=data["matches"])


@app.route("/bracket")
def bracket():
    data = load_data()
    matches = data["matches"]
    for m in matches:
        m["qualifier"] = get_qualifier(m)
        a1h = m.get("actual_leg1_home")
        a1a = m.get("actual_leg1_away")
        a2h = m.get("actual_leg2_home")
        a2a = m.get("actual_leg2_away")
        if all(v is not None for v in [a1h, a1a, a2h, a2a]):
            m["agg_home"] = a1h + a2a
            m["agg_away"] = a1a + a2h
        else:
            m["agg_home"] = None
            m["agg_away"] = None
    return render_template("bracket.html", matches=matches)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    data = load_data()

    if request.method == "POST":
        action = request.form.get("action")

        # Login
        if action == "login":
            pw = request.form.get("password", "")
            if pw == data["admin_password"]:
                session["is_admin"] = True
                flash("Admin access granted.", "success")
            else:
                flash("Wrong password.", "danger")
            return redirect(url_for("admin"))

        if not session.get("is_admin"):
            flash("Admin login required.", "danger")
            return redirect(url_for("admin"))

        # Add match
        if action == "add_match":
            new_id = max((m["id"] for m in data["matches"]), default=0) + 1
            data["matches"].append({
                "id": new_id,
                "home_team": request.form.get("home_team", "TBD"),
                "away_team": request.form.get("away_team", "TBD"),
                "leg1_deadline": request.form.get("leg1_deadline", ""),
                "leg2_deadline": request.form.get("leg2_deadline", ""),
                "actual_leg1_home": None,
                "actual_leg1_away": None,
                "actual_leg2_home": None,
                "actual_leg2_away": None,
            })
            save_data(data)
            flash("Match added.", "success")
            return redirect(url_for("admin"))

        # Edit match
        if action == "edit_match":
            mid = int(request.form.get("match_id", 0))
            match = next((m for m in data["matches"] if m["id"] == mid), None)
            if match:
                match["home_team"] = request.form.get("home_team", match["home_team"])
                match["away_team"] = request.form.get("away_team", match["away_team"])
                match["leg1_deadline"] = request.form.get("leg1_deadline", match["leg1_deadline"])
                match["leg2_deadline"] = request.form.get("leg2_deadline", match["leg2_deadline"])
                save_data(data)
                flash("Match updated.", "success")
            return redirect(url_for("admin"))

        # Enter results
        if action == "enter_results":
            mid = int(request.form.get("match_id", 0))
            match = next((m for m in data["matches"] if m["id"] == mid), None)
            if match:
                for field in ["actual_leg1_home", "actual_leg1_away", "actual_leg2_home", "actual_leg2_away"]:
                    val = request.form.get(field, "").strip()
                    match[field] = int(val) if val != "" else None
                save_data(data)
                flash("Results saved.", "success")
            return redirect(url_for("admin"))

        # Remove user
        if action == "remove_user":
            username_to_remove = request.form.get("username_to_remove", "").strip().lower()
            if username_to_remove in data["users"]:
                data["users"].remove(username_to_remove)
                data["predictions"].pop(username_to_remove, None)
                save_data(data)
                flash(f"User '{username_to_remove}' removed.", "success")
                if session.get("username") == username_to_remove:
                    session.pop("username", None)
            else:
                flash("User not found.", "danger")
            return redirect(url_for("admin"))

        # Delete match
        if action == "delete_match":
            mid = int(request.form.get("match_id", 0))
            data["matches"] = [m for m in data["matches"] if m["id"] != mid]
            # Clean up predictions for this match
            for user in data["predictions"]:
                data["predictions"][user].pop(str(mid), None)
            save_data(data)
            flash("Match deleted.", "success")
            return redirect(url_for("admin"))

    return render_template("admin.html", data=data, is_admin=session.get("is_admin", False))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
