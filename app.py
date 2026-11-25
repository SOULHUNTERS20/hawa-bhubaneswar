"""
app.py
------
The Flask web server for Hawa Bhubaneswar.

    python app.py          -> starts the site at http://127.0.0.1:5000

Layout of this file:
    1. Setup
    2. Helper functions (validation, converting rows for the browser)
    3. Page routes        (return HTML pages)
    4. API routes         (return JSON for the JavaScript on each page)
    5. Download routes    (.md and .csv)
    6. Admin routes       (password from the ADMIN_PASSWORD environment variable)
"""

import csv
import hmac
import io
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, send_file, session, url_for)

import admin_panel
import airquality
import assistant
import config
import storage
import study

# ===========================================================================
# 1. Setup
# ===========================================================================
app = Flask(__name__)
app.json.sort_keys = False  # keep the order we build (e.g. biggest exposure sources first)

# SECRET_KEY signs the admin login cookie. If you don't set one, a random key
# is made at startup (the only downside: admins get logged out on restart).
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # blocks other sites posting to /admin

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

IST = timezone(timedelta(hours=5, minutes=30))  # India Standard Time
TIME_FORMAT = "%Y-%m-%d %H:%M"
ID_PATTERN = re.compile(r"^BBSR-Z[1-5]-\d{3}$")
ZONES_BY_ID = {z["id"]: z for z in config.ZONES}


@app.context_processor
def add_template_globals():
    """Variables every HTML template can use."""
    return {
        "site_name": config.SITE_NAME,
        "zones": config.ZONES,
        "feel_options": config.FEEL_OPTIONS,
        "activity_options": config.ACTIVITY_OPTIONS,
        "note_max": config.NOTE_MAX_CHARS,
        "cfg": config,  # lets templates use the SOP settings (age groups, questions, ...)
    }


# ===========================================================================
# 2. Helpers
# ===========================================================================
def now_ist():
    return datetime.now(IST)


def to_number(text):
    """'42' -> 42.0, '' -> None, 'abc' -> raises ValueError."""
    text = str(text if text is not None else "").strip()
    return None if text == "" else float(text)


def check_range(raw, low, high, label, errors, whole_number=False):
    """Validate an optional number. Adds a message to `errors` if it's wrong."""
    try:
        value = to_number(raw)
    except ValueError:
        errors.append(f"{label} must be a number.")
        return None
    if value is None:
        return None
    if not (low <= value <= high):
        errors.append(f"{label} must be between {low} and {high}.")
        return None
    if whole_number:
        return int(round(value))
    return round(value, 1)


def row_for_browser(row):
    """Turn a markdown row (all text) into clean JSON with real numbers."""
    def num(key):
        try:
            return to_number(row.get(key))
        except ValueError:
            return None

    aqi = num("AQI")
    pm25 = num("PM2.5")
    # If someone only gave PM2.5 we still work out an AQI for charts.
    effective_aqi = aqi if aqi is not None else airquality.aqi_from_pm(pm25)
    zone_id = int(num("Zone") or 0)
    return {
        "timestamp": row["Timestamp"],
        "participant_id": row["Participant ID"],
        "zone_id": zone_id,
        "zone_name": ZONES_BY_ID.get(zone_id, {}).get("name", "Unknown"),
        "aqi": aqi,
        "pm25": pm25,
        "effective_aqi": effective_aqi,
        "temp": num("Temp (C)"),
        "feel": row["Feel"],
        "activity": row["Activity"],
        "note": row["Note"],
        "api_aqi": num("API AQI"),
        # Rows saved before stations were added have no source: they used the model.
        "ref_source": row.get("Ref source") or ("Model" if row["API AQI"] else ""),
        "flag": row["Flag"],
    }


def time_of_day(hour):
    """CSOD form question 3, worked out from the submission time."""
    if 5 <= hour < 12:
        return "Morning"
    if 12 <= hour < 17:
        return "Afternoon"
    if 17 <= hour < 21:
        return "Evening"
    return "Night"


def form_answers(raw, errors):
    """
    Check the optional "About your day" answers (the CSOD exercise's Google Form).
    Returns {column: value} ready to save. Unknown or empty answers are saved as "".
    """
    raw = raw if isinstance(raw, dict) else {}

    def one(key, options, label):
        value = raw.get(key) or ""
        if value == "":
            return ""
        if not isinstance(value, str) or value not in options:
            errors.append(f"Please choose a listed option for '{label}'.")
            return ""
        return value

    def many(key, options, label):
        values = raw.get(key) or []
        if not isinstance(values, list) or not all(isinstance(v, str) and v in options for v in values):
            errors.append(f"Please choose listed options for '{label}'.")
            return ""
        return "; ".join(v for v in options if v in values)  # keep the options' order

    answers = {
        "AQI source": one("aqi_source", config.AQI_SOURCES, "Where the AQI came from"),
        "Sky": one("sky", config.SKY_OPTIONS, "Sky"),
        "Humidity": one("humidity", config.HUMIDITY_OPTIONS, "Humidity"),
        "Activities today": many("activities", config.DAY_ACTIVITIES, "Activities today"),
        "Study place": one("study_place", config.STUDY_PLACES, "Where to study / work"),
        "Went outside": one("went_outside", ["Yes", "No"], "Did you go outside"),
        "App trigger": one("app_trigger", config.APP_TRIGGERS, "Why you open the AQI app"),
        "Poor AQI actions": many("poor_actions", config.POOR_AQI_ACTIONS, "Actions after a Poor AQI"),
        "App change wanted": one("app_change", config.APP_CHANGES, "Changes the AQI app needs"),
    }
    for column, question in config.FORM_SCALES:
        value = raw.get(column)
        if value in (None, ""):
            answers[column] = ""
        elif value in (1, 2, 3, 4, 5, "1", "2", "3", "4", "5"):
            answers[column] = int(value)
        else:
            errors.append(f"'{question}' must be 1 to 5.")
            answers[column] = ""
    return answers


def all_submissions():
    return [row_for_browser(r) for r in storage.read_submissions()]


# ===========================================================================
# 3. Page routes
# ===========================================================================
@app.route("/")
def home():
    return render_template("index.html", page="home")


@app.route("/map")
def live_map():
    return render_template("map.html", page="map")


@app.route("/live")
def live():
    return render_template("live.html", page="live")


@app.route("/calculator")
def calculator():
    return render_template("calculator.html", page="calculator")


@app.route("/submit")
def submit_page():
    return render_template("submit.html", page="submit")


@app.route("/participant")
def participant_page():
    return render_template("participant.html", page="participant")


@app.route("/data")
def data_page():
    return render_template("data.html", page="data")


@app.route("/ethics")
def ethics():
    return render_template("ethics.html", page="ethics")


@app.route("/ask")
def ask_page():
    return render_template("ask.html", page="ask", ask_enabled=assistant.is_enabled(),
                           ask_max=config.ASK_MAX_QUESTION_CHARS,
                           ask_per_hour=config.ASK_PER_VISITOR_PER_HOUR)


# ===========================================================================
# 4. API routes (JSON)
# ===========================================================================
@app.get("/api/live")
def api_live():
    return jsonify(airquality.get_live_data())


@app.get("/api/submissions")
def api_submissions():
    return jsonify(all_submissions())


@app.get("/api/summary")
def api_summary():
    """Counts + the latest readings for each zone (used by Home and Map)."""
    rows = all_submissions()
    zones = []
    for zone in config.ZONES:
        zone_rows = [r for r in rows if r["zone_id"] == zone["id"]]
        # Newest first. Timestamps are "YYYY-MM-DD HH:MM" so text sorting works.
        zone_rows.sort(key=lambda r: r["timestamp"], reverse=True)
        with_aqi = [r for r in zone_rows if r["effective_aqi"] is not None]
        zones.append({
            **zone,
            "count": len(zone_rows),
            "latest": with_aqi[0] if with_aqi else None,
            "recent": zone_rows[:3],
        })
    return jsonify({
        "submissions": len(rows),
        "participants": len(storage.read_participants()),
        "active_zones": len(config.ZONES),
        "zones": zones,
    })


@app.post("/api/participant")
def api_new_participant():
    """
    SOP items 1-6: consent + a new anonymous ID like BBSR-Z3-482, with city,
    residential zone, age group, gender and occupation/workplace.
    """
    data = request.get_json(silent=True) or {}
    try:
        zone_id = int(data.get("zone"))
    except (TypeError, ValueError):
        zone_id = None
    profile, errors = study.check_profile(data)
    if zone_id not in ZONES_BY_ID:
        errors.insert(0, "Please choose your residential zone.")
    if errors:
        return jsonify({"error": " ".join(errors), "errors": errors}), 400

    for _ in range(100):  # try random numbers until we find an unused one
        new_id = f"BBSR-Z{zone_id}-{secrets.randbelow(900) + 100}"
        saved = storage.add_participant_if_new({
            "Participant ID": new_id,
            "Zone": zone_id,
            "Created": now_ist().strftime(TIME_FORMAT),
            **profile,
        })
        if saved:
            return jsonify({"id": new_id, "zone": zone_id})
    return jsonify({"error": "This zone has run out of IDs. Please contact the team."}), 409


@app.get("/api/participant/<participant_id>")
def api_check_participant(participant_id):
    """Used by 'I already have an ID' to link an ID on a new device."""
    pid = storage.clean_text(participant_id).upper()
    row = storage.find_participant(pid) if ID_PATTERN.match(pid) else None
    if not row:
        return jsonify({"exists": False}), 404
    return jsonify({"exists": True, "id": pid, "zone": int(row["Zone"]),
                    "profile_complete": study.profile_complete(row)})


@app.post("/api/submit")
def api_submit():
    """Validate a survey submission on the server and save it."""
    data = request.get_json(silent=True) or {}
    errors = []

    # --- Participant ID + consent ---
    pid = storage.clean_text(data.get("participant_id")).upper()
    if not ID_PATTERN.match(pid):
        errors.append("Participant ID should look like BBSR-Z3-482.")
    elif not storage.find_participant(pid):
        errors.append("We don't recognise that participant ID. Get one on the 'My ID' page.")
    if data.get("consent") is not True:
        errors.append("Please tick the consent box.")

    # --- Zone ---
    try:
        zone_id = int(data.get("zone"))
    except (TypeError, ValueError):
        zone_id = None
    if zone_id not in ZONES_BY_ID:
        errors.append("Please choose a valid zone.")

    # --- Numbers (all optional, but must be in range if given) ---
    aqi = check_range(data.get("aqi"), 0, 500, "AQI", errors, whole_number=True)
    pm25 = check_range(data.get("pm25"), 0, 999, "PM2.5", errors)
    temp = check_range(data.get("temp"), -5, 55, "Temperature", errors)

    # --- Text fields ---
    feel = storage.clean_text(data.get("feel"))
    if feel not in config.FEEL_OPTIONS:
        errors.append("Please choose how the air smells / feels.")
    activity = storage.clean_text(data.get("activity"))
    if activity not in config.ACTIVITY_OPTIONS:
        errors.append("Please choose what you were doing.")
    note = storage.clean_text(data.get("note"))
    if len(note) > config.NOTE_MAX_CHARS:
        errors.append(f"Note must be {config.NOTE_MAX_CHARS} characters or less.")

    # --- "About your day" (CSOD Google Form questions, all optional) ---
    day = form_answers(data.get("day"), errors)

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    # --- Rate limit: 1 submission per ID per RATE_LIMIT_HOURS ---
    now = now_ist()
    previous = [r["Timestamp"] for r in storage.read_submissions() if r["Participant ID"] == pid]
    if previous:
        last = datetime.strptime(max(previous), TIME_FORMAT).replace(tzinfo=IST)
        wait = last + timedelta(hours=config.RATE_LIMIT_HOURS) - now
        if wait.total_seconds() > 0:
            minutes = int(wait.total_seconds() // 60) + 1
            return jsonify({"ok": False, "errors": [
                f"You can submit once every {config.RATE_LIMIT_HOURS} hours. "
                f"Please try again in about {minutes} minutes."
            ]}), 429

    # --- Flag (never delete) readings far away from the reference value ---
    # Reference = the official CPCB station if the zone has one, otherwise the model.
    api_aqi, ref_source = airquality.reference_for_zone(zone_id)
    community_aqi = aqi if aqi is not None else airquality.aqi_from_pm(pm25)
    flag = ""
    if api_aqi is not None and community_aqi is not None:
        difference = abs(community_aqi - api_aqi)
        if difference > config.FLAG_DIFF_AQI:
            compared_with = "the CPCB station" if ref_source == "CPCB station" else "the model"
            flag = f"Differs from {compared_with} by {difference}"

    storage.add_submission({
        "Timestamp": now.strftime(TIME_FORMAT),
        "Participant ID": pid,
        "Zone": zone_id,
        "AQI": "" if aqi is None else aqi,
        "PM2.5": "" if pm25 is None else pm25,
        "Temp (C)": "" if temp is None else temp,
        "Feel": feel,
        "Activity": activity,
        "Note": note,
        "API AQI": "" if api_aqi is None else api_aqi,
        "Flag": flag,
        "Ref source": ref_source if api_aqi is not None else "",
        "Time of day": time_of_day(now.hour),
        **day,
    })
    return jsonify({"ok": True, "flagged": bool(flag)})


@app.post("/api/ask")
def api_ask():
    """Ask Hawa: send a question to the AI assistant. Questions are NOT stored."""
    if not assistant.is_enabled():
        return jsonify({"ok": False, "error": "Ask Hawa is switched off right now."}), 503

    data = request.get_json(silent=True) or {}
    question = storage.clean_text(data.get("question"))
    if not question:
        return jsonify({"ok": False, "error": "Please type a question."}), 400
    if len(question) > config.ASK_MAX_QUESTION_CHARS:
        return jsonify({"ok": False, "error":
                        f"Please keep questions under {config.ASK_MAX_QUESTION_CHARS} characters."}), 400
    history = data.get("history") if isinstance(data.get("history"), list) else []
    history = [h for h in history if isinstance(h, dict)]

    # Each browser gets a random id in its (signed) session cookie, used only for the hourly limit.
    if "ask_id" not in session:
        session["ask_id"] = assistant.new_visitor_id()
    limit_error = assistant.check_and_count(session["ask_id"])
    if limit_error:
        return jsonify({"ok": False, "error": limit_error}), 429

    try:
        answer = assistant.ask(question, history)
    except assistant.AskError as error:
        return jsonify({"ok": False, "error": str(error)}), 502
    return jsonify({"ok": True, "answer": answer})


# ===========================================================================
# 5. Downloads
# ===========================================================================
@app.get("/download/submissions.md")
def download_md():
    storage.read_submissions()  # makes sure the file exists
    return send_file(storage.SUBMISSIONS_FILE, as_attachment=True,
                     download_name="hawa-bhubaneswar-submissions.md",
                     mimetype="text/markdown")


@app.get("/download/submissions.csv")
def download_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(storage.SUBMISSION_COLUMNS)
    for row in storage.read_submissions():
        cells = []
        for col in storage.SUBMISSION_COLUMNS:
            value = row[col]
            # Stop spreadsheet apps treating free text as a formula (=, +, @...)
            if col in ("Note", "Flag") and value[:1] in ("=", "+", "-", "@"):
                value = "'" + value
            cells.append(value)
        writer.writerow(cells)
    return Response(
        "﻿" + output.getvalue(),  # ﻿ helps Excel read UTF-8 correctly
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=hawa-bhubaneswar-submissions.csv"},
    )


# ===========================================================================
# 6. Admin
# ===========================================================================
def is_admin():
    return session.get("admin") is True


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not ADMIN_PASSWORD:
        return render_template("admin.html", page="admin", mode="disabled")

    error = None
    if request.method == "POST":
        typed = request.form.get("password", "")
        # compare_digest avoids leaking how many characters were right
        if hmac.compare_digest(typed.encode(), ADMIN_PASSWORD.encode()):
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Wrong password."

    if not is_admin():
        return render_template("admin.html", page="admin", mode="login", error=error)

    # The tables themselves are loaded by static/js/admin.js from admin_panel.py
    return render_template("admin.html", page="admin", mode="dashboard",
                           stats=admin_panel.overview(now_ist().strftime(TIME_FORMAT)))


@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


# The Standard Operating Protocol pages and APIs live in study.py,
# the admin panel's table editor in admin_panel.py
app.register_blueprint(study.bp)
app.register_blueprint(admin_panel.bp)


# ===========================================================================
# Start the development server
# ===========================================================================
if __name__ == "__main__":
    if not ADMIN_PASSWORD:
        print("Note: ADMIN_PASSWORD is not set, so the admin page is switched off.")
    app.run(debug=True)
