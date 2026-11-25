"""
admin.py
--------
The admin panel's data editor (team / teacher only).

The admin page (app.py -> /admin) loads each table from these JSON routes and
lets a logged-in admin search, edit and delete rows, verify hotspots, and
withdraw a participant (deletes everything linked to their ID, as promised on
the Ethics page).

Every change sends back the row exactly as the admin saw it. If the file was
changed in the meantime (a new submission, another admin), nothing is saved
and the admin is asked to reload, so the wrong row can never be overwritten.
"""

import os
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request, session

import config
import storage

bp = Blueprint("admin_api", __name__)

ZONE_IDS = [str(z["id"]) for z in config.ZONES]
MARKER_FILE = os.path.join(storage.DATA_DIR, "DEMO_DATA")


def choice(options):
    return {"type": "choice", "options": list(options)}


def number(low, high, whole=False, blank=True):
    return {"type": "number", "min": low, "max": high, "whole": whole, "blank": blank}


def text(max_len):
    return {"type": "text", "max": max_len}


# What the admin can see and change in each table. Columns not listed under
# "edit" are shown but locked (IDs, timestamps, values worked out by the site).
TABLES = {
    "readings": {
        "label": "Readings", "table": storage.SUBMISSIONS, "newest_first": True,
        "show": ["Timestamp", "Participant ID", "Zone", "AQI", "PM2.5", "Temp (C)", "Feel", "Activity",
                 "Note", "API AQI", "Ref source", "Flag"],
        "edit": {"Zone": choice(ZONE_IDS), "AQI": number(0, 500, whole=True), "PM2.5": number(0, 999),
                 "Temp (C)": number(-5, 55), "Feel": choice(config.FEEL_OPTIONS),
                 "Activity": choice(config.ACTIVITY_OPTIONS), "Note": text(config.NOTE_MAX_CHARS),
                 "Flag": text(150)},
    },
    "participants": {
        "label": "Participants", "table": storage.PARTICIPANTS, "newest_first": True,
        "show": storage.PARTICIPANT_COLUMNS,
        "edit": {"Zone": choice(ZONE_IDS), "Age group": choice(config.AGE_GROUPS),
                 "Gender": choice(config.GENDERS), "Occupation": choice(config.OCCUPATIONS),
                 "Workplace": choice(config.WORKPLACES)},
    },
    "diary": {
        "label": "Diary", "table": storage.DIARY, "newest_first": True,
        "show": ["Date", "Participant ID", "Day", "Start", "End", "Location", "Activity", "Hours",
                 "Outdoor PM2.5", "Infiltration", "Breathing rate", "PAQE (ug)"],
        "edit": {"Location": choice(config.MICROENVIRONMENTS), "Activity": choice(config.ACTIVITIES),
                 "Outdoor PM2.5": number(0, 999, blank=False)},
    },
    "survey": {
        "label": "Surveys", "table": storage.SURVEY, "newest_first": True,
        "show": storage.SURVEY["columns"],
        "edit": {**{f"Q{i}": number(1, 5, whole=True, blank=False) for i in range(1, 7)},
                 "Practices": text(150), "Persist": choice(["", "Yes", "No"])},
    },
    "checkins": {
        "label": "Check-ins", "table": storage.CHECKINS, "newest_first": True,
        "show": storage.CHECKINS["columns"],
        "edit": {"Checked app (4h)": choice(["Yes", "No"]), "Plan changes": text(150),
                 "Anxiety (1-5)": number(1, 5, whole=True, blank=False)},
    },
    "hotspots": {
        "label": "Hotspots", "table": storage.HOTSPOTS, "newest_first": True,
        "show": storage.HOTSPOTS["columns"],
        "edit": {"Zone": choice(ZONE_IDS), "Type": choice(config.HOTSPOT_TYPES), "Landmark": text(80),
                 "Description": text(200), "Status": choice(config.HOTSPOT_STATUSES),
                 "Verification note": text(150)},
    },
}


def is_admin():
    return session.get("admin") is True


def _fail(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def _clean_value(column, rule, raw):
    """Check one edited value against its rule. Returns (value, error)."""
    value = storage.clean_text(raw)
    if rule["type"] == "choice":
        if value not in rule["options"]:
            return None, f"{column}: choose one of the listed options."
        return value, None
    if rule["type"] == "text":
        if len(value) > rule["max"]:
            return None, f"{column}: keep it under {rule['max']} characters."
        return value, None
    # number
    if value == "":
        return ("", None) if rule["blank"] else (None, f"{column} can't be empty.")
    try:
        num = float(value)
    except ValueError:
        return None, f"{column} must be a number."
    if not (rule["min"] <= num <= rule["max"]):
        return None, f"{column} must be between {rule['min']} and {rule['max']}."
    return (int(round(num)) if rule["whole"] else round(num, 1)), None


def _recalculate(name, row):
    """Keep worked-out columns in step with the edited ones."""
    if name == "diary":
        factor = config.MICROENVIRONMENTS[row["Location"]]["factor"]
        rate = config.ACTIVITIES[row["Activity"]]["rate"]
        outdoor = float(row["Outdoor PM2.5"])
        hours = float(row["Hours"] or 0)
        row.update({"Infiltration": factor, "Breathing rate": rate, "Micro PM2.5": round(outdoor * factor, 1),
                    "PAQE (ug)": round(hours * outdoor * factor * rate, 1)})
    elif name == "survey":
        scores = [int(row[f"Q{i}"]) for i in range(1, 7)]
        row["DRS"] = round(sum(scores) / len(scores), 2)
    elif name == "hotspots":
        row["Verification method"] = config.HOTSPOT_TYPES.get(row["Type"], row["Verification method"])
    return row


@bp.get("/admin/api/<name>")
def api_table(name):
    if not is_admin():
        return _fail("Please log in again.", 401)
    spec = TABLES.get(name)
    if not spec:
        return _fail("Unknown table.", 404)
    rows = storage.read_table(spec["table"])
    return jsonify({"ok": True, "label": spec["label"], "show": spec["show"], "edit": spec["edit"],
                    "rows": [{"i": i, "row": r} for i, r in enumerate(rows)]})


@bp.post("/admin/api/<name>/update")
def api_update(name):
    if not is_admin():
        return _fail("Please log in again.", 401)
    spec = TABLES.get(name)
    data = request.get_json(silent=True)
    if not spec or not isinstance(data, dict) or not isinstance(data.get("original"), dict):
        return _fail("Bad request.")
    try:
        index = int(data.get("index"))
    except (TypeError, ValueError):
        return _fail("Bad request.")

    fields, errors = {}, []
    for column, raw in (data.get("fields") or {}).items():
        rule = spec["edit"].get(column)
        if not rule:
            continue  # locked column: ignore
        value, error = _clean_value(column, rule, raw)
        if error:
            errors.append(error)
        else:
            fields[column] = value
    if errors:
        return _fail(" ".join(errors))

    merged = _recalculate(name, {**data["original"], **fields})
    changed = {k: v for k, v in merged.items() if k in spec["table"]["columns"]}
    if not storage.update_row(spec["table"], index, data["original"], changed):
        return _fail("This row changed since you opened the page. Reload and try again.", 409)
    return jsonify({"ok": True, "row": {k: storage.clean_text(v) for k, v in changed.items()}})


@bp.post("/admin/api/<name>/delete")
def api_delete(name):
    if not is_admin():
        return _fail("Please log in again.", 401)
    spec = TABLES.get(name)
    data = request.get_json(silent=True)
    if not spec or not isinstance(data, dict) or not isinstance(data.get("original"), dict):
        return _fail("Bad request.")
    try:
        index = int(data.get("index"))
    except (TypeError, ValueError):
        return _fail("Bad request.")
    if not storage.delete_row(spec["table"], index, data["original"]):
        return _fail("This row changed since you opened the page. Reload and try again.", 409)
    return jsonify({"ok": True})


@bp.post("/admin/api/withdraw")
def api_withdraw():
    """Remove a participant and everything linked to their ID (consent withdrawn)."""
    if not is_admin():
        return _fail("Please log in again.", 401)
    data = request.get_json(silent=True) or {}
    pid = storage.clean_text(data.get("participant_id")).upper()
    if not storage.find_participant(pid):
        return _fail("No participant with that ID.", 404)
    removed = {
        "readings": storage.delete_where(storage.SUBMISSIONS, "Participant ID", pid),
        "diary": storage.delete_where(storage.DIARY, "Participant ID", pid),
        "survey": storage.delete_where(storage.SURVEY, "Participant ID", pid),
        "checkins": storage.delete_where(storage.CHECKINS, "Participant ID", pid),
        "participants": storage.delete_where(storage.PARTICIPANTS, "Participant ID", pid),
    }
    # Hotspot reports stay in the public register, but no longer point to the person.
    storage.blank_where(storage.HOTSPOTS, "Reporter ID", pid)
    return jsonify({"ok": True, "removed": removed})


@bp.post("/admin/api/clear-sample")
def api_clear_sample():
    """Empty every table. Only allowed while the sample dataset is loaded."""
    if not is_admin():
        return _fail("Please log in again.", 401)
    if (request.get_json(silent=True) or {}).get("confirm") != "CLEAR":
        return _fail("Type CLEAR to confirm.")
    if not os.path.exists(MARKER_FILE):
        return _fail("The data here is real study data, so it can't be cleared from this page.", 403)
    for spec in TABLES.values():
        storage.replace_table(spec["table"], [])
    os.remove(MARKER_FILE)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Overview numbers for the top of the admin page
# ---------------------------------------------------------------------------
def _num(text_value):
    try:
        return float(text_value)
    except (TypeError, ValueError):
        return None


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def overview(now_text):
    """now_text: current IST time as 'YYYY-MM-DD HH:MM'."""
    participants = storage.read_participants()
    readings = storage.read_submissions()
    diary = storage.read_table(storage.DIARY)
    survey = storage.read_table(storage.SURVEY)
    hotspots = storage.read_table(storage.HOTSPOTS)

    days = {}
    for r in diary:
        days.setdefault(r["Participant ID"], set()).add(r["Date"])
    by_phase = {p: [r for r in survey if r["Phase"] == p] for p in config.SURVEY_PHASES}
    after = by_phase[config.SURVEY_PHASES[-1]]
    persist = [r["Persist"] for r in after if r["Persist"]]
    since = (datetime.strptime(now_text, "%Y-%m-%d %H:%M") - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
    paqe_by_day = {}
    for r in diary:
        key = (r["Participant ID"], r["Date"])
        paqe_by_day[key] = paqe_by_day.get(key, 0) + (_num(r["PAQE (ug)"]) or 0)

    return {
        "sample": os.path.exists(MARKER_FILE),
        "participants": len(participants),
        "target": config.REGISTRATION_TARGET,
        "zones": {z["id"]: sum(1 for p in participants if p["Zone"] == str(z["id"])) for z in config.ZONES},
        "zone_names": {z["id"]: z["name"] for z in config.ZONES},
        "diarists": len(days),
        "completed": sum(1 for d in days.values() if len(d) >= config.STUDY_DAYS),
        "avg_days": round(sum(len(d) for d in days.values()) / len(days), 1) if days else 0,
        "study_days": config.STUDY_DAYS,
        "mean_paqe": round(_mean(list(paqe_by_day.values())) or 0),
        "before": len(by_phase[config.SURVEY_PHASES[0]]),
        "after": len(after),
        "drs_before": _mean([_num(r["DRS"]) for r in by_phase[config.SURVEY_PHASES[0]]]),
        "drs_after": _mean([_num(r["DRS"]) for r in after]),
        "persist_yes": sum(1 for p in persist if p == "Yes"),
        "persist_total": len(persist),
        "hotspots": len(hotspots),
        "verified": sum(1 for h in hotspots if h["Status"] == "Verified"),
        "pending": sum(1 for h in hotspots if h["Status"] == "Reported"),
        "readings": len(readings),
        "readings_24h": sum(1 for r in readings if r["Timestamp"] >= since),
        "flagged": sum(1 for r in readings if r["Flag"]),
    }
