import json
import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import lru_cache
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "ucl-forecast-secret-key-change-me"

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

DEFAULT_DATA = {
    "users": {},
    "admin_password": "admin123",
    "matches": [],
    "predictions": {},
}


def get_cached_time():
    if "now" not in g:
        g.now = datetime.now()
    return g.now


@lru_cache(maxsize=1)
def load_data_cached():
    return load_data()


def invalidate_cache():
    load_data_cached.cache_clear()


def migrate_data(data):
    """Convert list-based users to dict-based. Saves file if migration needed."""
    if isinstance(data["users"], list):
        old_list = data["users"]
        data["users"] = {
            username: {
                "email": None,
                "password_hash": None,
                "reset_token": None,
                "reset_expires": None,
            }
            for username in old_list
        }
        save_data(data)
    return data


def load_data():
    if not os.path.exists(DATA_FILE):
        save_data(DEFAULT_DATA)
        return DEFAULT_DATA.copy()
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    data = migrate_data(data)
    return data


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
    invalidate_cache()


def user_profile_complete(user_record):
    """Returns True if the user has both password_hash and email set."""
    if user_record is None:
        return False
    return (
        user_record.get("password_hash") is not None
        and user_record.get("email") is not None
    )


def send_reset_email(to_address, reset_url):
    """Send password reset email. Returns False silently if SMTP not configured."""
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    if not smtp_user or not smtp_pass:
        return False
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    msg = MIMEText(
        f"Hello,\n\nClick the link below to reset your UCL Forecast password:\n\n"
        f"{reset_url}\n\n"
        "This link expires in 1 hour. If you did not request a reset, ignore this email."
    )
    msg["Subject"] = "UCL Forecast — Password Reset"
    msg["From"] = smtp_from
    msg["To"] = to_address

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [to_address], msg.as_string())
    except Exception:
        return False
    return True


def get_match_by_id(matches, match_id):
    if not hasattr(g, "_match_cache") or g._match_cache.get("matches") is not matches:
        g._match_cache = {"matches": matches, "lookup": {m["id"]: m for m in matches}}
    return g._match_cache["lookup"].get(match_id)


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
    for user in data["users"].keys():
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
        return get_cached_time() >= deadline
    except (ValueError, TypeError):
        return False


@app.before_request
def before_request():
    get_cached_time()


@app.route("/")
def home():
    if session.get("username"):
        return redirect(url_for("dashboard"))
    return render_template("home.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    if not username:
        flash("Please enter a username.", "danger")
        return redirect(url_for("home"))

    data = load_data()
    user_record = data["users"].get(username)
    if user_record is None:
        flash("Invalid username or password.", "danger")
        return redirect(url_for("home"))

    if user_record.get("password_hash") is None:
        # Migrated user with no password yet — let them in to set one
        session["username"] = username
        flash("Please set an email and password to continue.", "warning")
        return redirect(url_for("complete_profile"))

    if not check_password_hash(user_record["password_hash"], password):
        flash("Invalid username or password.", "danger")
        return redirect(url_for("home"))

    session["username"] = username
    flash(f"Welcome back, {username}!", "success")
    return redirect(url_for("dashboard"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("username"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password or not confirm_password:
            flash("All fields are required.", "danger")
            return render_template("register.html")

        if len(username) > 20:
            flash("Username must be 20 characters or fewer.", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("register.html")

        data = load_data()

        if username in data["users"]:
            flash("Username already taken.", "danger")
            return render_template("register.html")

        for record in data["users"].values():
            if record.get("email") == email:
                flash("Email already in use.", "danger")
                return render_template("register.html")

        if len(data["users"]) >= 12:
            flash("Maximum 12 users reached. Registration is closed.", "danger")
            return render_template("register.html")

        data["users"][username] = {
            "email": email,
            "password_hash": generate_password_hash(password),
            "reset_token": None,
            "reset_expires": None,
        }
        data["predictions"][username] = {}
        save_data(data)
        session["username"] = username
        flash(f"Account created! Welcome, {username}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/complete-profile", methods=["GET", "POST"])
def complete_profile():
    username = session.get("username")
    if not username:
        return redirect(url_for("home"))
    data = load_data()
    user_record = data["users"].get(username)
    if user_record is None:
        session.pop("username", None)
        return redirect(url_for("home"))
    if user_profile_complete(user_record):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not password or not confirm_password:
            flash("All fields are required.", "danger")
            return render_template("complete_profile.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("complete_profile.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("complete_profile.html")

        for uname, record in data["users"].items():
            if uname != username and record.get("email") == email:
                flash("Email already in use.", "danger")
                return render_template("complete_profile.html")

        user_record["email"] = email
        user_record["password_hash"] = generate_password_hash(password)
        save_data(data)
        flash("Profile complete! Welcome back.", "success")
        return redirect(url_for("dashboard"))

    return render_template("complete_profile.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        flash("If that email is registered, a reset link has been sent.", "info")
        data = load_data()
        matched_username = None
        for uname, record in data["users"].items():
            if record.get("email") == email:
                matched_username = uname
                break
        if matched_username:
            token = secrets.token_urlsafe(32)
            expires = (datetime.now() + timedelta(hours=1)).isoformat()
            data["users"][matched_username]["reset_token"] = token
            data["users"][matched_username]["reset_expires"] = expires
            save_data(data)
            base_url = os.environ.get("APP_BASE_URL", "http://localhost:5000")
            reset_url = f"{base_url}/reset-password/{token}"
            send_reset_email(email, reset_url)
        return redirect(url_for("forgot_password"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    data = load_data()
    matched_username = None
    for uname, record in data["users"].items():
        if record.get("reset_token") == token:
            matched_username = uname
            break

    if matched_username is None:
        flash("Invalid or expired link.", "danger")
        return redirect(url_for("forgot_password"))

    user_record = data["users"][matched_username]
    expires_str = user_record.get("reset_expires")
    if expires_str is None or datetime.fromisoformat(expires_str) < datetime.now():
        user_record["reset_token"] = None
        user_record["reset_expires"] = None
        save_data(data)
        flash("This reset link has expired. Please request a new one.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password or not confirm_password:
            flash("Both fields are required.", "danger")
            return render_template("reset_password.html", token=token)

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("reset_password.html", token=token)

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("reset_password.html", token=token)

        user_record["password_hash"] = generate_password_hash(password)
        user_record["reset_token"] = None
        user_record["reset_expires"] = None
        save_data(data)
        flash("Password updated! Please sign in.", "success")
        return redirect(url_for("home"))

    return render_template("reset_password.html", token=token)


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
    if not user_profile_complete(data["users"].get(username)):
        return redirect(url_for("complete_profile"))
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
    if not user_profile_complete(data["users"].get(username)):
        return redirect(url_for("complete_profile"))

    match = get_match_by_id(data["matches"], match_id)
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
            match = get_match_by_id(data["matches"], mid)
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
            match = get_match_by_id(data["matches"], mid)
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
                del data["users"][username_to_remove]
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
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
