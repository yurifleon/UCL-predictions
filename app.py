import json
import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import lru_cache
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "ucl-forecast-secret-key-change-me"


@app.template_filter("deadline_tz")
def deadline_tz_filter(iso_str):
    """Convert a UTC ISO deadline string to ET and Bogota/Lima (COT) for display."""
    if not iso_str:
        return ""
    try:
        dt_utc = datetime.fromisoformat(iso_str)
        # March-April 2026: CDT = UTC-5 (same as Lima)
        dt_ct = dt_utc - timedelta(hours=5)
        fmt = "%b %d, %I:%M %p"
        return f"{dt_ct.strftime(fmt)} CT / LIM"
    except (ValueError, TypeError):
        return iso_str

_data_dir = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(_data_dir, "data.json")

DEFAULT_DATA = {
    "users": {},
    "admin_password": "Barca4ever!",
    "matches": [],
    "predictions": {},
}

# Deadlines stored in UTC. March 2026: Europe on CET (UTC+1), so UCL kick-offs
# 18:45 CET = 17:45 UTC, 21:00 CET = 20:00 UTC.
# Display offsets: EDT = UTC-4, COT (Bogota/Lima) = UTC-5.
# Order matches to match bracket image pairings: (1,2)→QF1, (3,4)→QF2, (5,6)→QF3, (7,8)→QF4.
SEED_MATCHES = [
    {"round": "r16", "home_team": "PSG",             "away_team": "Chelsea",       "leg1_deadline": "2026-03-11T20:00:00", "leg2_deadline": "2026-03-17T20:00:00"},
    {"round": "r16", "home_team": "Galatasaray",     "away_team": "Liverpool",     "leg1_deadline": "2026-03-10T17:45:00", "leg2_deadline": "2026-03-18T20:00:00"},
    {"round": "r16", "home_team": "Real Madrid",     "away_team": "Man City",      "leg1_deadline": "2026-03-11T20:00:00", "leg2_deadline": "2026-03-17T20:00:00"},
    {"round": "r16", "home_team": "Atalanta",        "away_team": "Bayern Munich", "leg1_deadline": "2026-03-10T20:00:00", "leg2_deadline": "2026-03-18T20:00:00"},
    {"round": "r16", "home_team": "Newcastle",       "away_team": "Barcelona",     "leg1_deadline": "2026-03-10T20:00:00", "leg2_deadline": "2026-03-18T17:45:00"},
    {"round": "r16", "home_team": "Atletico Madrid", "away_team": "Tottenham",     "leg1_deadline": "2026-03-10T20:00:00", "leg2_deadline": "2026-03-18T20:00:00"},
    {"round": "r16", "home_team": "Bodo/Glimt",      "away_team": "Sporting CP",   "leg1_deadline": "2026-03-11T20:00:00", "leg2_deadline": "2026-03-17T17:45:00"},
    {"round": "r16", "home_team": "Bayer Leverkusen","away_team": "Arsenal",       "leg1_deadline": "2026-03-11T17:45:00", "leg2_deadline": "2026-03-17T20:00:00"},
]

SUPPORTED_LANGS = {"en", "es"}

SPANISH_TRANSLATIONS = {
    "Dashboard": "Panel",
    "Leaderboard": "Clasificacion",
    "Bracket": "Cuadro",
    "Admin": "Admin",
    "Logout": "Cerrar sesion",
    "Please enter a username.": "Por favor, introduce un nombre de usuario.",
    "Invalid username or password.": "Usuario o contrasena invalidos.",
    "Please set an email and password to continue.": (
        "Configura un correo y una contrasena para continuar."
    ),
    "Welcome back, {username}!": "Bienvenido de nuevo, {username}!",
    "All fields are required.": "Todos los campos son obligatorios.",
    "Username must be 20 characters or fewer.": "El nombre de usuario debe tener 20 caracteres o menos.",
    "Passwords do not match.": "Las contrasenas no coinciden.",
    "Password must be at least 6 characters.": "La contrasena debe tener al menos 6 caracteres.",
    "Username already taken.": "Ese nombre de usuario ya esta en uso.",
    "Email already in use.": "Ese correo ya esta en uso.",
    "Maximum 12 users reached. Registration is closed.": (
        "Se alcanzo el maximo de 12 usuarios. El registro esta cerrado."
    ),
    "Account created! Welcome, {username}!": "Cuenta creada. Bienvenido, {username}!",
    "Profile complete! Welcome back.": "Perfil completado. Bienvenido de nuevo.",
    "If that email is registered, a reset link has been sent.": (
        "Si ese correo esta registrado, se envio un enlace para restablecer la contrasena."
    ),
    "Invalid or expired link.": "Enlace invalido o caducado.",
    "This reset link has expired. Please request a new one.": (
        "Este enlace de restablecimiento ha caducado. Solicita uno nuevo."
    ),
    "Both fields are required.": "Ambos campos son obligatorios.",
    "Password updated! Please sign in.": "Contrasena actualizada. Inicia sesion.",
    "Match not found.": "Partido no encontrado.",
    "Prediction saved!": "Pronostico guardado.",
    "Admin access granted.": "Acceso de admin concedido.",
    "Wrong password.": "Contrasena incorrecta.",
    "Admin login required.": "Se requiere iniciar sesion como admin.",
    "Match added.": "Partido agregado.",
    "Match updated.": "Partido actualizado.",
    "Results saved.": "Resultados guardados.",
    "User '{username}' removed.": "Usuario '{username}' eliminado.",
    "Admin created account for {username}.": "Admin creo la cuenta para {username}.",
    "User not found.": "Usuario no encontrado.",
    "Match deleted.": "Partido eliminado.",
    "UCL Forecast - Sign In": "UCL Forecast - Iniciar sesion",
    "UCL Round of 16 Forecast": "Pronostico UCL de Octavos de Final",
    "Sign in to your account": "Inicia sesion en tu cuenta",
    "Username": "Usuario",
    "Enter username": "Introduce usuario",
    "Password": "Contrasena",
    "Enter password": "Introduce contrasena",
    "Sign In": "Iniciar sesion",
    "Forgot password?": "Olvidaste tu contrasena?",
    "New here? Create an account": "Eres nuevo? Crea una cuenta",
    "UCL Forecast - Register": "UCL Forecast - Registro",
    "Create Account": "Crear cuenta",
    "Join the UCL Forecast game": "Unete al juego UCL Forecast",
    "Choose a username": "Elige un usuario",
    "Email": "Correo",
    "At least 6 characters": "Al menos 6 caracteres",
    "Confirm Password": "Confirmar contrasena",
    "Repeat password": "Repite la contrasena",
    "Already have an account? Sign in": "Ya tienes cuenta? Inicia sesion",
    "UCL Forecast - Complete Profile": "UCL Forecast - Completar perfil",
    "Complete Your Profile": "Completa tu perfil",
    "Your account predates passwords. Please set an email and password to continue.": (
        "Tu cuenta es anterior al sistema de contrasenas. Configura correo y contrasena para continuar."
    ),
    "New Password": "Nueva contrasena",
    "Save & Continue": "Guardar y continuar",
    "UCL Forecast - Forgot Password": "UCL Forecast - Recuperar contrasena",
    "Reset Password": "Restablecer contrasena",
    "Enter your email to receive a reset link": (
        "Introduce tu correo para recibir un enlace de restablecimiento"
    ),
    "Send Reset Link": "Enviar enlace de restablecimiento",
    "Back to sign in": "Volver a iniciar sesion",
    "UCL Forecast - Set New Password": "UCL Forecast - Nueva contrasena",
    "Set New Password": "Establecer nueva contrasena",
    "Update Password": "Actualizar contrasena",
    "Dashboard - UCL Forecast": "Panel - UCL Forecast",
    "Round of 16 Matches": "Partidos de octavos",
    "No matches configured yet. Ask the admin to set them up.": (
        "Aun no hay partidos configurados. Pide al admin que los cree."
    ),
    "Locked": "Cerrado",
    "Predict": "Pronosticar",
    "Update Forecast": "Actualizar pronostico",
    "Your Prediction": "Tu pronostico",
    "Leg 1:": "Ida:",
    "Leg 2:": "Vuelta:",
    "No prediction yet.": "Aun no hay pronostico.",
    "Make one": "Haz uno",
    "Actual Results": "Resultados reales",
    "pts": "pts",
    "Leg 1 deadline:": "Cierre ida:",
    "Leg 1: locked": "Ida: cerrada",
    "Leg 2 deadline:": "Cierre vuelta:",
    "Leg 2: locked": "Vuelta: cerrada",
    "User": "Usuario",
    "Points": "Puntos",
    "Full Leaderboard": "Clasificacion completa",
    "Predict - {home} vs {away}": "Pronosticar - {home} vs {away}",
    "Leg 1 ({team} home)": "Ida ({team} local)",
    "Deadline:": "Cierre:",
    "Leg 2 ({team} home)": "Vuelta ({team} local)",
    "Save Prediction": "Guardar pronostico",
    "Both legs are locked. No changes allowed.": (
        "Las dos piernas estan cerradas. No se permiten cambios."
    ),
    "Back to Dashboard": "Volver al panel",
    "Leaderboard - UCL Forecast": "Clasificacion - UCL Forecast",
    "Rank": "Puesto",
    "Total": "Total",
    "Scoring System": "Sistema de puntuacion",
    "Exact score:": "Marcador exacto:",
    "6 points (per leg)": "6 puntos (por partido)",
    "Correct result + goal difference:": "Resultado correcto + diferencia de goles:",
    "4 points (per leg)": "4 puntos (por partido)",
    "Correct result only:": "Solo resultado correcto:",
    "2 points (per leg)": "2 puntos (por partido)",
    "Max per tie:": "Maximo por eliminatoria:",
    "12 points (6 + 6)": "12 puntos (6 + 6)",
    "Bracket - UCL Forecast": "Cuadro - UCL Forecast",
    "Tournament Bracket": "Cuadro del torneo",
    "Round of 16": "Octavos de final",
    "Quarter-finals": "Cuartos de final",
    "Semi-finals": "Semifinales",
    "Final": "Final",
    "Champion": "Campeon",
    "TBD": "Por definir",
    "vs": "vs",
    "Admin - UCL Forecast": "Admin - UCL Forecast",
    "Admin Panel": "Panel de admin",
    "Admin Login": "Inicio de admin",
    "Login": "Entrar",
    "Registered Users ({count}/12)": "Usuarios registrados ({count}/12)",
    "No users registered yet.": "Aun no hay usuarios registrados.",
    "Create User (Admin)": "Crear usuario (admin)",
    "Create a user with initial login password": "Crear un usuario con contrasena inicial",
    "Temporary Password": "Contrasena temporal",
    "Set initial password": "Define una contrasena inicial",
    "Create User": "Crear usuario",
    "Remove user {user}? Their predictions will be deleted.": (
        "Eliminar usuario {user}? Sus pronosticos se borraran."
    ),
    "Add Round of 16 Match": "Agregar partido de octavos",
    "Home Team (Leg 1)": "Equipo local (ida)",
    "Away Team (Leg 1)": "Equipo visitante (ida)",
    "Leg 1 Deadline": "Cierre ida",
    "Leg 2 Deadline": "Cierre vuelta",
    "Add Match": "Agregar partido",
    "Match {id}:": "Partido {id}:",
    "Delete this match?": "Eliminar este partido?",
    "Delete": "Eliminar",
    "Edit Match Details": "Editar datos del partido",
    "Home Team": "Equipo local",
    "Away Team": "Equipo visitante",
    "Update Details": "Actualizar datos",
    "Enter Results": "Cargar resultados",
    "Leg 1: {team} goals": "Ida: goles de {team}",
    "Leg 2: {team} goals (home)": "Vuelta: goles de {team} (local)",
    "Leg 2: {team} goals (away)": "Vuelta: goles de {team} (visitante)",
    "Save Results": "Guardar resultados",
    "No matches yet. Add one above.": "Aun no hay partidos. Agrega uno arriba.",
    "English": "Ingles",
    "Spanish": "Espanol",
    "Language": "Idioma",
    "UCL Forecast - Password Reset": "UCL Forecast - Restablecer contrasena",
    "Hello,\n\nClick the link below to reset your UCL Forecast password:\n\n{reset_url}\n\nThis link expires in 1 hour. If you did not request a reset, ignore this email.": (
        "Hola,\n\nHaz clic en el siguiente enlace para restablecer tu contrasena de UCL Forecast:\n\n{reset_url}\n\n"
        "Este enlace caduca en 1 hora. Si no solicitaste el restablecimiento, ignora este correo."
    ),
}


def translate(text: str, **kwargs) -> str:
    lang = getattr(g, "lang", session.get("lang", "en"))
    translated = SPANISH_TRANSLATIONS.get(text, text) if lang == "es" else text
    translated_text = str(translated)
    return translated_text.format(**kwargs) if kwargs else translated_text


def _is_safe_next_url(target):
    if not target:
        return False
    parsed = urlparse(target)
    return parsed.scheme == "" and parsed.netloc == ""


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
    migration_needed = False
    if isinstance(data["users"], list):
        old_list = data["users"]
        data["users"] = {
            username: {
                "email": None,
                "password_hash": None,
                "reset_token": None,
                "reset_expires": None,
                "preferred_lang": None,
            }
            for username in old_list
        }
        migration_needed = True

    for user_record in data["users"].values():
        if "preferred_lang" not in user_record:
            user_record["preferred_lang"] = None
            migration_needed = True

    for match in data.get("matches", []):
        if "round" not in match:
            match["round"] = "r16"
            migration_needed = True

    if not data.get("matches"):
        data["matches"] = [
            {
                "id": i + 1,
                "actual_leg1_home": None,
                "actual_leg1_away": None,
                "actual_leg2_home": None,
                "actual_leg2_away": None,
                **m,
            }
            for i, m in enumerate(SEED_MATCHES)
        ]
        migration_needed = True

    if migration_needed:
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
        translate(
            "Hello,\n\nClick the link below to reset your UCL Forecast password:\n\n"
            "{reset_url}\n\n"
            "This link expires in 1 hour. If you did not request a reset, ignore this email.",
            reset_url=reset_url,
        )
    )
    msg["Subject"] = translate("UCL Forecast - Password Reset")
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

    # Scoring tier by round: R16 uses 6/4/2; QF and beyond use 10/7/5
    if match.get("round", "r16") == "r16":
        pts_exact, pts_gd, pts_result = 6, 4, 2
    else:
        pts_exact, pts_gd, pts_result = 10, 7, 5

    # Check leg 1
    a1h = match.get("actual_leg1_home")
    a1a = match.get("actual_leg1_away")
    if a1h is not None and a1a is not None:
        p1h = prediction.get("leg1_home")
        p1a = prediction.get("leg1_away")
        if p1h is not None and p1a is not None:
            if p1h == a1h and p1a == a1a:
                points["leg1"] = pts_exact
            else:
                actual_outcome = (a1h > a1a) - (a1h < a1a)
                pred_outcome = (p1h > p1a) - (p1h < p1a)
                if actual_outcome == pred_outcome:
                    points["leg1"] = pts_gd if (a1h - a1a) == (p1h - p1a) else pts_result

    # Check leg 2
    a2h = match.get("actual_leg2_home")
    a2a = match.get("actual_leg2_away")
    if a2h is not None and a2a is not None:
        p2h = prediction.get("leg2_home")
        p2a = prediction.get("leg2_away")
        if p2h is not None and p2a is not None:
            if p2h == a2h and p2a == a2a:
                points["leg2"] = pts_exact
            else:
                actual_outcome = (a2h > a2a) - (a2h < a2a)
                pred_outcome = (p2h > p2a) - (p2h < p2a)
                if actual_outcome == pred_outcome:
                    points["leg2"] = pts_gd if (a2h - a2a) == (p2h - p2a) else pts_result

    points["total"] = points["leg1"] + points["leg2"]
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
    lang = None
    username = session.get("username")
    if username:
        data = load_data_cached()
        user_record = data["users"].get(username)
        if user_record:
            user_lang = user_record.get("preferred_lang")
            if user_lang in SUPPORTED_LANGS:
                lang = user_lang

    if lang is None:
        lang = session.get("lang")
    if lang not in SUPPORTED_LANGS:
        best = request.accept_languages.best_match(["en", "es"])
        lang = best if best in SUPPORTED_LANGS else "en"

    session["lang"] = lang
    g.lang = lang
    get_cached_time()


@app.context_processor
def inject_i18n_helpers():
    return {
        "_": translate,
        "current_lang": getattr(g, "lang", "en"),
    }


@app.route("/set-language/<lang>")
def set_language(lang):
    if lang in SUPPORTED_LANGS:
        session["lang"] = lang
        username = session.get("username")
        if username:
            data = load_data()
            user_record = data["users"].get(username)
            if user_record is not None and user_record.get("preferred_lang") != lang:
                user_record["preferred_lang"] = lang
                save_data(data)
    next_url = request.args.get("next")
    if next_url and _is_safe_next_url(next_url):
        return redirect(next_url)
    return redirect(url_for("home"))


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
        flash(translate("Please enter a username."), "danger")
        return redirect(url_for("home"))

    data = load_data()
    user_record = data["users"].get(username)
    if user_record is None:
        flash(translate("Invalid username or password."), "danger")
        return redirect(url_for("home"))

    if user_record.get("password_hash") is None:
        # Migrated user with no password yet — let them in to set one
        session["username"] = username
        user_lang = user_record.get("preferred_lang")
        if user_lang in SUPPORTED_LANGS:
            session["lang"] = user_lang
        flash(translate("Please set an email and password to continue."), "warning")
        return redirect(url_for("complete_profile"))

    if not check_password_hash(user_record["password_hash"], password):
        flash(translate("Invalid username or password."), "danger")
        return redirect(url_for("home"))

    session["username"] = username
    user_lang = user_record.get("preferred_lang")
    if user_lang in SUPPORTED_LANGS:
        session["lang"] = user_lang
    flash(translate("Welcome back, {username}!", username=username), "success")
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
            flash(translate("All fields are required."), "danger")
            return render_template("register.html")

        if len(username) > 20:
            flash(translate("Username must be 20 characters or fewer."), "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash(translate("Passwords do not match."), "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash(translate("Password must be at least 6 characters."), "danger")
            return render_template("register.html")

        data = load_data()

        if username in data["users"]:
            flash(translate("Username already taken."), "danger")
            return render_template("register.html")

        for record in data["users"].values():
            if record.get("email") == email:
                flash(translate("Email already in use."), "danger")
                return render_template("register.html")

        if len(data["users"]) >= 12:
            flash(translate("Maximum 12 users reached. Registration is closed."), "danger")
            return render_template("register.html")

        data["users"][username] = {
            "email": email,
            "password_hash": generate_password_hash(password),
            "reset_token": None,
            "reset_expires": None,
            "preferred_lang": session.get("lang", "en"),
        }
        data["predictions"][username] = {}
        save_data(data)
        session["username"] = username
        flash(translate("Account created! Welcome, {username}!", username=username), "success")
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
            flash(translate("All fields are required."), "danger")
            return render_template("complete_profile.html")

        if password != confirm_password:
            flash(translate("Passwords do not match."), "danger")
            return render_template("complete_profile.html")

        if len(password) < 6:
            flash(translate("Password must be at least 6 characters."), "danger")
            return render_template("complete_profile.html")

        for uname, record in data["users"].items():
            if uname != username and record.get("email") == email:
                flash(translate("Email already in use."), "danger")
                return render_template("complete_profile.html")

        user_record["email"] = email
        user_record["password_hash"] = generate_password_hash(password)
        if user_record.get("preferred_lang") not in SUPPORTED_LANGS:
            user_record["preferred_lang"] = session.get("lang", "en")
        save_data(data)
        flash(translate("Profile complete! Welcome back."), "success")
        return redirect(url_for("dashboard"))

    return render_template("complete_profile.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        flash(translate("If that email is registered, a reset link has been sent."), "info")
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
        flash(translate("Invalid or expired link."), "danger")
        return redirect(url_for("forgot_password"))

    user_record = data["users"][matched_username]
    expires_str = user_record.get("reset_expires")
    if expires_str is None or datetime.fromisoformat(expires_str) < datetime.now():
        user_record["reset_token"] = None
        user_record["reset_expires"] = None
        save_data(data)
        flash(translate("This reset link has expired. Please request a new one."), "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password or not confirm_password:
            flash(translate("Both fields are required."), "danger")
            return render_template("reset_password.html", token=token)

        if password != confirm_password:
            flash(translate("Passwords do not match."), "danger")
            return render_template("reset_password.html", token=token)

        if len(password) < 6:
            flash(translate("Password must be at least 6 characters."), "danger")
            return render_template("reset_password.html", token=token)

        user_record["password_hash"] = generate_password_hash(password)
        user_record["reset_token"] = None
        user_record["reset_expires"] = None
        save_data(data)
        flash(translate("Password updated! Please sign in."), "success")
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
        flash(translate("Match not found."), "danger")
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
        flash(translate("Prediction saved!"), "success")
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
            effective_admin_pw = os.environ.get("ADMIN_PASSWORD") or data["admin_password"]
            if pw == effective_admin_pw:
                session["is_admin"] = True
                flash(translate("Admin access granted."), "success")
            else:
                flash(translate("Wrong password."), "danger")
            return redirect(url_for("admin"))

        if not session.get("is_admin"):
            flash(translate("Admin login required."), "danger")
            return redirect(url_for("admin"))

        # Add user with initial password
        if action == "add_user":
            username = request.form.get("username", "").strip().lower()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not username or not email or not password or not confirm_password:
                flash(translate("All fields are required."), "danger")
                return redirect(url_for("admin"))

            if len(username) > 20:
                flash(translate("Username must be 20 characters or fewer."), "danger")
                return redirect(url_for("admin"))

            if password != confirm_password:
                flash(translate("Passwords do not match."), "danger")
                return redirect(url_for("admin"))

            if len(password) < 6:
                flash(translate("Password must be at least 6 characters."), "danger")
                return redirect(url_for("admin"))

            if username in data["users"]:
                flash(translate("Username already taken."), "danger")
                return redirect(url_for("admin"))

            for record in data["users"].values():
                if record.get("email") == email:
                    flash(translate("Email already in use."), "danger")
                    return redirect(url_for("admin"))

            if len(data["users"]) >= 12:
                flash(translate("Maximum 12 users reached. Registration is closed."), "danger")
                return redirect(url_for("admin"))

            data["users"][username] = {
                "email": email,
                "password_hash": generate_password_hash(password),
                "reset_token": None,
                "reset_expires": None,
                "preferred_lang": session.get("lang", "en"),
            }
            data["predictions"][username] = {}
            save_data(data)
            flash(translate("Admin created account for {username}.", username=username), "success")
            return redirect(url_for("admin"))

        # Add match
        if action == "add_match":
            new_id = max((m["id"] for m in data["matches"]), default=0) + 1
            data["matches"].append({
                "id": new_id,
                "round": request.form.get("round", "r16"),
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
            flash(translate("Match added."), "success")
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
                flash(translate("Match updated."), "success")
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
                flash(translate("Results saved."), "success")
            return redirect(url_for("admin"))

        # Remove user
        if action == "remove_user":
            username_to_remove = request.form.get("username_to_remove", "").strip().lower()
            if username_to_remove in data["users"]:
                del data["users"][username_to_remove]
                data["predictions"].pop(username_to_remove, None)
                save_data(data)
                flash(translate("User '{username}' removed.", username=username_to_remove), "success")
                if session.get("username") == username_to_remove:
                    session.pop("username", None)
            else:
                flash(translate("User not found."), "danger")
            return redirect(url_for("admin"))

        # Delete match
        if action == "delete_match":
            mid = int(request.form.get("match_id", 0))
            data["matches"] = [m for m in data["matches"] if m["id"] != mid]
            # Clean up predictions for this match
            for user in data["predictions"]:
                data["predictions"][user].pop(str(mid), None)
            save_data(data)
            flash(translate("Match deleted."), "success")
            return redirect(url_for("admin"))

    return render_template("admin.html", data=data, is_admin=session.get("is_admin", False))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
