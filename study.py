"""
study.py
--------
Everything from the Standard Operating Protocol (SOP), Group A:

  1-6  Consent + anonymous ID + city, zone, age group, gender, occupation/workplace
  7    14-day time-activity diary with hourly PM2.5, PAQE and personalized alerts
  8    Decision-making questions (5-point Likert) -> Decision Responsiveness Score
  9    Citizen-reported pollution hotspot register with student verification
  10   Do exposure-management behaviours persist after the intervention? (Yes/No)
       + the General AQI Advisory page

This file is a Flask "Blueprint": a group of pages and API routes that app.py
plugs into the website with  app.register_blueprint(study.bp).

Privacy: profiles and diaries are only shown publicly as GROUP TOTALS. The raw
files (with participant IDs) can only be downloaded from the admin page.
"""

import csv
import io
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, url_for

import airquality
import config
import exposure
import storage

bp = Blueprint("study", __name__)

IST = timezone(timedelta(hours=5, minutes=30))
TIME_FORMAT = "%Y-%m-%d %H:%M"
ID_PATTERN = re.compile(r"^BBSR-Z[1-5]-\d{3}$")
PROFILE_FIELDS = {"Age group": "AGE_GROUPS", "Gender": "GENDERS",
                  "Occupation": "OCCUPATIONS", "Workplace": "WORKPLACES"}


def now_ist():
    return datetime.now(IST)


def find_registered(raw_id):
    pid = storage.clean_text(raw_id).upper()
    if not ID_PATTERN.match(pid):
        return pid, None
    return pid, storage.find_participant(pid)


def profile_complete(row):
    return bool(row) and all(row.get(f) for f in PROFILE_FIELDS) and row.get("Consent", "").startswith("Yes")


def check_profile(data):
    """Validate SOP items 1, 4, 5, 6 from a form. Returns (fields, errors)."""
    errors, fields = [], {}
    if data.get("consent") is not True:
        errors.append("Please tick the consent box (SOP item 1).")
    for column, option_list in PROFILE_FIELDS.items():
        value = storage.clean_text(data.get(column.lower().replace(" ", "_")))
        if value not in getattr(config, option_list):
            errors.append(f"Please choose your {column.lower()}.")
        fields[column] = value
    fields["City"] = config.CITY
    fields["Consent"] = "Yes " + now_ist().strftime(TIME_FORMAT)
    return fields, errors


# ===========================================================================
# Pages
# ===========================================================================
@bp.route("/participate")
def participate_page():
    return render_template("participate.html", page="participate")


@bp.route("/diary")
def diary_page():
    sample_rows, sample_total = exposure.sop_sample()
    return render_template("diary.html", page="participate", sample_rows=sample_rows, sample_total=sample_total,
                           today=exposure.today().isoformat())


@bp.route("/survey")
def survey_page():
    return render_template("survey.html", page="participate")


@bp.route("/hotspots")
def hotspots_page():
    return render_template("hotspots.html", page="participate")


@bp.route("/advisory")
def advisory_page():
    # Any picture put in static/posters/ is shown on the page ("use posters here").
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "posters")
    posters = []
    if os.path.isdir(folder):
        posters = sorted(f for f in os.listdir(folder)
                         if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")))
    return render_template("advisory.html", page="advisory", posters=posters)


# ===========================================================================
# Registration profile (SOP items 1-6)
# ===========================================================================
@bp.post("/api/participant/<participant_id>/profile")
def api_profile(participant_id):
    pid, row = find_registered(participant_id)
    if not row:
        return jsonify({"ok": False, "errors": ["We don't recognise that participant ID."]}), 404
    fields, errors = check_profile(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    storage.update_participant(pid, fields)
    return jsonify({"ok": True})


@bp.get("/api/study/status/<participant_id>")
def api_status(participant_id):
    """Where one participant is in the SOP (used by the Take part page)."""
    pid, row = find_registered(participant_id)
    registered = len(storage.read_participants())
    if not row:
        return jsonify({"registered": False, "count": registered, "target": config.REGISTRATION_TARGET})
    diary_dates = sorted({r["Date"] for r in storage.read_table(storage.DIARY) if r["Participant ID"] == pid})
    phases = sorted({r["Phase"] for r in storage.read_table(storage.SURVEY) if r["Participant ID"] == pid})
    hotspots = sum(1 for r in storage.read_table(storage.HOTSPOTS) if r["Reporter ID"] == pid)
    readings = sum(1 for r in storage.read_submissions() if r["Participant ID"] == pid)
    return jsonify({
        "registered": True, "id": pid, "zone": int(row["Zone"] or 0),
        "profile_complete": profile_complete(row),
        "days_logged": len(diary_dates), "study_days": config.STUDY_DAYS,
        "last_diary_date": diary_dates[-1] if diary_dates else None,
        "survey_phases": phases, "hotspots": hotspots, "readings": readings,
        "count": registered, "target": config.REGISTRATION_TARGET,
    })


# ===========================================================================
# Time-activity diary + PAQE + alerts (SOP item 7, parts A-C)
# ===========================================================================
def _hour_text(h):
    """6 -> '06:00', 30 -> '06:00+1' (next day). Stored in the diary file."""
    return f"{h % 24:02d}:00" + ("+1" if h >= 24 else "")


def _hour_value(text):
    try:
        return int(text[:2]) + (24 if text.endswith("+1") else 0)
    except (TypeError, ValueError):
        return None


def _diary_blocks(rows):
    blocks = []
    for r in rows:
        start, end = _hour_value(r["Start"]), _hour_value(r["End"])
        if start is not None and end is not None:
            blocks.append({"start": start, "end": end, "location": r["Location"], "activity": r["Activity"]})
    return blocks


def _usual_day(pid):
    """The participant's most recent diary day, or the SOP's standard day."""
    rows = [r for r in storage.read_table(storage.DIARY) if r["Participant ID"] == pid]
    if rows:
        last = max(r["Date"] for r in rows)
        blocks, _ = exposure.validate_blocks(_diary_blocks([r for r in rows if r["Date"] == last]))
        if blocks:
            return blocks
    return [dict(b) for b in config.SOP_STANDARD_DAY]


def _parse_date(text):
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        return None


@bp.get("/api/diary/<participant_id>")
def api_diary_get(participant_id):
    pid, row = find_registered(participant_id)
    if not row:
        return jsonify({"ok": False, "error": "Unknown participant ID."}), 404
    day = _parse_date(request.args.get("date")) or exposure.today()
    rows = [r for r in storage.read_table(storage.DIARY) if r["Participant ID"] == pid]
    saved = [r for r in rows if r["Date"] == day.isoformat()]
    return jsonify({
        "ok": True,
        "date": day.isoformat(),
        "blocks": _diary_blocks(saved) if saved else _usual_day(pid),
        "saved": bool(saved),
        "days_logged": len({r["Date"] for r in rows}),
        "study_days": config.STUDY_DAYS,
    })


@bp.post("/api/diary")
def api_diary_save():
    data = request.get_json(silent=True) or {}
    pid, row = find_registered(data.get("participant_id"))
    if not row:
        return jsonify({"ok": False, "error": "Please get or link your participant ID first."}), 400
    day = _parse_date(data.get("date"))
    first_allowed = max(_parse_date((row.get("Created") or "")[:10]) or date.min,
                        exposure.today() - timedelta(days=30))
    if not day or day > exposure.today() or day < first_allowed:
        return jsonify({"ok": False, "error": "Choose a date between your registration day and today."}), 400
    blocks, error = exposure.validate_blocks(data.get("blocks"))
    if error:
        return jsonify({"ok": False, "error": error}), 400
    zone_id = int(row["Zone"] or 0) or 1
    try:
        result = exposure.compute_day(zone_id, day, blocks)
    except Exception as err:
        print("Diary PM2.5 lookup failed:", type(err).__name__, err)
        return jsonify({"ok": False, "error": "Couldn't get hourly PM2.5 data for that day right now (the free "
                        "data services are busy). Please try again later."}), 502

    earlier = sorted({r["Date"] for r in storage.read_table(storage.DIARY) if r["Participant ID"] == pid})
    first_day = min([_parse_date(d) for d in earlier] + [day])
    day_no = (day - first_day).days + 1
    # replace_diary_day also renumbers the person's other days if this one is earlier
    storage.replace_diary_day(pid, day.isoformat(), [{
        "Date": day.isoformat(), "Participant ID": pid, "Day": day_no,
        "Start": _hour_text(r["start"]), "End": _hour_text(r["end"]),
        "Location": r["location"], "Activity": r["activity"], "Hours": r["hours"],
        "Outdoor PM2.5": "" if r["outdoor"] is None else r["outdoor"],
        "Infiltration": r["factor"], "Breathing rate": r["rate"],
        "Micro PM2.5": "" if r["micro"] is None else r["micro"],
        "PAQE (ug)": "" if r["paqe"] is None else r["paqe"],
        "Source": result["source"],
    } for r in result["rows"]])
    days_logged = len(set(earlier) | {day.isoformat()})
    return jsonify({"ok": True, **result, "date": day.isoformat(), "day_no": day_no,
                    "days_logged": days_logged, "study_days": config.STUDY_DAYS})


@bp.get("/api/alert/<participant_id>")
def api_alert(participant_id):
    """Today's personalized alert: the person's usual day vs today's hourly forecast."""
    pid, row = find_registered(participant_id)
    if not row:
        return jsonify({"ok": False, "error": "Unknown participant ID."}), 404
    try:
        result = exposure.forecast_alert(int(row["Zone"] or 0) or 1, _usual_day(pid))
    except Exception as err:
        print("Alert PM2.5 lookup failed:", type(err).__name__, err)
        return jsonify({"ok": False, "error": "Forecast data isn't available right now."}), 502
    return jsonify({"ok": True, **result})


# ===========================================================================
# Decision-making survey + DRS + persistence (SOP items 8 and 10)
# ===========================================================================
@bp.post("/api/survey")
def api_survey():
    data = request.get_json(silent=True) or {}
    pid, row = find_registered(data.get("participant_id"))
    errors = []
    if not row:
        errors.append("Please get or link your participant ID first.")
    phase = data.get("phase")
    if phase not in config.SURVEY_PHASES:
        errors.append("Please choose whether this is before or after the alerts.")
    answers = data.get("answers")
    m = len(config.DECISION_QUESTIONS)
    if not (isinstance(answers, list) and len(answers) == m and all(a in (1, 2, 3, 4, 5) for a in answers)):
        errors.append("Please answer every question (1 = Never ... 5 = Always).")
    practices = data.get("practices") if isinstance(data.get("practices"), list) else []
    practices = [p for p in practices if isinstance(p, str) and p in config.PROTECTIVE_PRACTICES]
    persist = data.get("persist", "")
    if phase == config.SURVEY_PHASES[-1] and persist not in ("Yes", "No"):
        errors.append("Please answer the last question with Yes or No.")
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    drs = round(sum(answers) / m, 2)  # DRS = sum of S_k / m
    rows = storage.replace_survey_answer({  # one answer per participant per phase
        "Timestamp": now_ist().strftime(TIME_FORMAT), "Participant ID": pid, "Phase": phase,
        **{f"Q{i + 1}": a for i, a in enumerate(answers)}, "DRS": drs,
        "Practices": "; ".join(practices),
        "Persist": persist if phase == config.SURVEY_PHASES[-1] else ""})

    before = next((float(r["DRS"]) for r in rows
                   if r["Participant ID"] == pid and r["Phase"] == config.SURVEY_PHASES[0] and r["DRS"]), None)
    change = round(drs - before, 2) if before is not None and phase != config.SURVEY_PHASES[0] else None
    return jsonify({"ok": True, "drs": drs, "change": change})


# ===========================================================================
# Hotspot register (SOP item 9)
# ===========================================================================
def _public_hotspots():
    rows = storage.read_table(storage.HOTSPOTS)
    return [{k: r[k] for k in ("Timestamp", "Zone", "Type", "Landmark", "Description",
                               "Verification method", "Status", "Verification note")}
            for r in reversed(rows)]  # newest first; reporter IDs are never shown publicly


@bp.get("/api/hotspots")
def api_hotspots():
    return jsonify(_public_hotspots())


@bp.post("/api/hotspot")
def api_hotspot():
    data = request.get_json(silent=True) or {}
    pid, row = find_registered(data.get("participant_id"))
    errors = []
    if not row:
        errors.append("Please get or link your participant ID first.")
    try:
        zone_id = int(data.get("zone"))
    except (TypeError, ValueError):
        zone_id = None
    if zone_id not in {z["id"] for z in config.ZONES}:
        errors.append("Please choose the zone.")
    kind = data.get("type")
    if not isinstance(kind, str) or kind not in config.HOTSPOT_TYPES:
        errors.append("Please choose what you observed.")
    landmark = storage.clean_text(data.get("landmark"))
    description = storage.clean_text(data.get("description"))
    if not landmark or len(landmark) > 80:
        errors.append("Please give a nearby landmark (up to 80 characters), not a home address.")
    if len(description) > 200:
        errors.append("Please keep the description under 200 characters.")
    if data.get("safe") is not True:
        errors.append("Please confirm you observed this from a safe place.")
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    today_text = now_ist().strftime("%Y-%m-%d")
    mine_today = [r for r in storage.read_table(storage.HOTSPOTS)
                  if r["Reporter ID"] == pid and r["Timestamp"].startswith(today_text)]
    if len(mine_today) >= config.HOTSPOTS_PER_ID_PER_DAY:
        return jsonify({"ok": False, "errors": ["You've reached today's limit of hotspot reports."]}), 429

    storage.append_row(storage.HOTSPOTS, {
        "Timestamp": now_ist().strftime(TIME_FORMAT), "Reporter ID": pid, "Zone": zone_id,
        "Type": kind, "Landmark": landmark, "Description": description,
        "Verification method": config.HOTSPOT_TYPES[kind], "Status": "Reported", "Verification note": "",
    })
    return jsonify({"ok": True})


# ===========================================================================
# Pollution spike check-in (CSOD Phase 3 micro-survey)
# ===========================================================================
def city_aqi():
    """City AQI now: the CPCB station where a zone has one, otherwise the model (same as Home/Advisory)."""
    try:
        live = airquality.get_live_data()
    except Exception:
        return None
    values = [(z.get("station") or {}).get("aqi") or z.get("aqi") for z in live.get("zones", [])]
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values)) if values else None


@bp.route("/checkin")
def checkin_page():
    return render_template("checkin.html", page="checkin")


@bp.get("/api/spike")
def api_spike():
    """Is the city air at a 'spike' level right now? Used to show the check-in prompt."""
    aqi = city_aqi()
    return jsonify({"aqi": aqi, "spike": aqi is not None and aqi >= config.SPIKE_AQI,
                    "threshold": config.SPIKE_AQI})


@bp.post("/api/checkin")
def api_checkin():
    data = request.get_json(silent=True) or {}
    pid, row = find_registered(data.get("participant_id"))
    errors = []
    if not row:
        errors.append("Please get or link your participant ID first.")
    checked = data.get("checked_app")
    if checked not in ("Yes", "No"):
        errors.append("Please say whether you looked at an AQI app in the last 4 hours.")
    changes = data.get("plan_changes") if isinstance(data.get("plan_changes"), list) else []
    changes = [c for c in config.PLAN_CHANGES if c in changes]
    if not changes:
        errors.append("Please choose how it changed your plans (or 'No change').")
    elif "No change" in changes and len(changes) > 1:
        errors.append("'No change' can't be combined with other answers.")
    anxiety = data.get("anxiety")
    if anxiety not in (1, 2, 3, 4, 5):
        errors.append("Please rate your pollution anxiety from 1 to 5.")
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    now = now_ist()
    since = (now - timedelta(hours=config.CHECKIN_EVERY_HOURS)).strftime(TIME_FORMAT)
    recent = [r for r in storage.read_table(storage.CHECKINS)
              if r["Participant ID"] == pid and r["Timestamp"] >= since]
    if recent:
        return jsonify({"ok": False, "errors": [
            f"You already checked in during the last {config.CHECKIN_EVERY_HOURS} hours. Thank you!"]}), 429

    aqi = city_aqi()
    storage.append_row(storage.CHECKINS, {
        "Timestamp": now.strftime(TIME_FORMAT), "Participant ID": pid, "Zone": row["Zone"],
        "City AQI": "" if aqi is None else aqi, "Checked app (4h)": checked,
        "Plan changes": "; ".join(changes), "Anxiety (1-5)": anxiety,
    })
    return jsonify({"ok": True})


# ===========================================================================
# Weekly insights per zone ("This week in your zone")
# ===========================================================================
def _effective_aqi(r):
    aqi = _num(r.get("AQI"))
    if aqi is None:
        aqi = airquality.aqi_from_pm(_num(r.get("PM2.5")))
    return aqi


def _hour_bucket(timestamp):
    try:
        hour = int(timestamp[11:13])
    except ValueError:
        return None
    return "morning" if 5 <= hour < 12 else "afternoon" if hour < 17 else "evening" if hour < 21 else "night"


def _band(aqi):
    for limit, name in ((50, "Good"), (100, "Satisfactory"), (200, "Moderate"), (300, "Poor"), (400, "Very Poor")):
        if aqi <= limit:
            return name
    return "Severe"


def weekly_insights():
    now = now_ist()
    week_start = (now - timedelta(days=7)).strftime(TIME_FORMAT)
    prev_start = (now - timedelta(days=14)).strftime(TIME_FORMAT)
    readings = storage.read_submissions()
    hotspots = storage.read_table(storage.HOTSPOTS)
    people = {p["Participant ID"]: p["Zone"] for p in storage.read_participants()}
    diary = [r for r in storage.read_table(storage.DIARY) if r["Date"] >= week_start[:10]]

    zones = []
    for zone in config.ZONES:
        zid = str(zone["id"])
        week = [r for r in readings if r["Zone"] == zid and r["Timestamp"] >= week_start]
        prev = [r for r in readings if r["Zone"] == zid and prev_start <= r["Timestamp"] < week_start]
        values = [v for v in (_effective_aqi(r) for r in week) if v is not None]
        lines = []
        mean = round(sum(values) / len(values)) if values else None
        if mean is not None:
            refs = [(_effective_aqi(r), _num(r["API AQI"])) for r in week]
            refs = [(c, o) for c, o in refs if c is not None and o]
            source = "the CPCB station" if zone.get("station") else "the satellite model"
            text = f"Community readings averaged AQI {mean} ({_band(mean)}) from {len(values)} readings"
            if refs:
                gap = round(100 * (sum(c for c, _ in refs) - sum(o for _, o in refs)) / sum(o for _, o in refs))
                text += f", {abs(gap)}% {'above' if gap >= 0 else 'below'} {source}" if abs(gap) >= 3 \
                    else f", close to {source}"
            lines.append(text + ".")

            prev_values = [v for v in (_effective_aqi(r) for r in prev) if v is not None]
            if len(prev_values) >= 3:
                change = round(100 * (mean - sum(prev_values) / len(prev_values)) / (sum(prev_values) / len(prev_values)))
                if abs(change) >= 5:
                    lines.append(f"That is {abs(change)}% {'worse' if change > 0 else 'better'} than the week before.")

            buckets = defaultdict(list)
            for r in week:
                v, b = _effective_aqi(r), _hour_bucket(r["Timestamp"])
                if v is not None and b:
                    buckets[b].append(v)
            buckets = {b: sum(v) / len(v) for b, v in buckets.items() if len(v) >= 2}
            if len(buckets) >= 2:
                worst = max(buckets, key=buckets.get)
                extra = round(100 * (buckets[worst] - mean) / mean)
                if extra >= 5:
                    lines.append(f"Worst in the {worst}: about {extra}% above the zone's weekly average.")

        spots = [h for h in hotspots if h["Zone"] == zid and h["Timestamp"] >= week_start]
        if spots:
            top = Counter(h["Type"] for h in spots).most_common(1)[0][0]
            verified = sum(1 for h in spots if h["Status"] == "Verified")
            lines.append(f"{len(spots)} hotspot report{'s' if len(spots) != 1 else ''}, mostly "
                         f"{top.lower()} ({verified} verified).")

        totals, by_place = defaultdict(float), defaultdict(float)
        for r in diary:
            if people.get(r["Participant ID"]) == zid and _num(r["PAQE (ug)"]) is not None:
                totals[(r["Participant ID"], r["Date"])] += _num(r["PAQE (ug)"])
                by_place[config.MICROENVIRONMENTS.get(r["Location"], {}).get("label", "Other").split(":")[0]] \
                    += _num(r["PAQE (ug)"])
        if totals:
            daily = round(sum(totals.values()) / len(totals))
            place = max(by_place, key=by_place.get)
            share = round(100 * by_place[place] / sum(by_place.values()))
            lines.append(f"Residents breathed in about {daily} µg of PM2.5 a day; {share}% of it "
                         f"{'at home' if place == 'Home' else 'at work' if place == 'Workplace' else 'on the road' if place == 'Road' else 'outdoors'}.")

        zones.append({"id": zone["id"], "name": zone["name"], "mean": mean, "lines": lines})

    ranked = [z for z in zones if z["mean"] is not None]
    headline = ""
    if len(ranked) >= 2:
        worst = max(ranked, key=lambda z: z["mean"])
        best = min(ranked, key=lambda z: z["mean"])
        headline = (f"Zone {worst['id']} ({worst['name']}) had the worst air this week, "
                    f"Zone {best['id']} ({best['name']}) the cleanest.")
    return {"from": week_start[:10], "to": now.strftime("%Y-%m-%d"), "headline": headline, "zones": zones}


@bp.get("/api/insights")
def api_insights():
    return jsonify(weekly_insights())


# ===========================================================================
# Study summary for the Data page (group totals only)
# ===========================================================================
def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def _num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


@bp.get("/api/study-summary")
def api_study_summary():
    people = storage.read_participants()
    zone_of = {p["Participant ID"]: p["Zone"] for p in people}

    registration = {
        "count": len(people), "target": config.REGISTRATION_TARGET,
        "complete_profiles": sum(1 for p in people if profile_complete(p)),
        "by_zone": Counter(p["Zone"] for p in people),
    }
    for column in PROFILE_FIELDS:
        registration["by_" + column.split()[0].lower()] = Counter(p[column] for p in people if p[column])

    # Diary: daily totals per participant-day
    diary = storage.read_table(storage.DIARY)
    day_totals, by_location = defaultdict(float), defaultdict(float)
    for r in diary:
        paqe = _num(r["PAQE (ug)"])
        if paqe is None:
            continue
        day_totals[(r["Participant ID"], r["Date"])] += paqe
        label = config.MICROENVIRONMENTS.get(r["Location"], {}).get("label", r["Location"])
        by_location[label.split(":")[0]] += paqe
    all_paqe = sum(by_location.values()) or 1
    per_person_days = Counter(pid for pid, _ in day_totals)
    by_zone = defaultdict(list)
    by_date = defaultdict(list)
    for (pid, d), total in day_totals.items():
        by_zone[zone_of.get(pid, "?")].append(total)
        by_date[d].append(total)
    diary_summary = {
        "participants": len(per_person_days),
        "person_days": len(day_totals),
        "completed": sum(1 for n in per_person_days.values() if n >= config.STUDY_DAYS),
        "study_days": config.STUDY_DAYS,
        "mean_daily_paqe": _mean(list(day_totals.values())),
        "share_by_location": {k: round(100 * v / all_paqe) for k, v in
                              sorted(by_location.items(), key=lambda kv: -kv[1])},
        "mean_by_zone": {z: _mean(v) for z, v in sorted(by_zone.items())},
        "trend": [{"date": d, "mean": _mean(v)} for d, v in sorted(by_date.items())],
    }

    # Survey: DRS per phase, per-question means, paired change, persistence
    survey = storage.read_table(storage.SURVEY)
    phases = {}
    for phase in config.SURVEY_PHASES:
        rows = [r for r in survey if r["Phase"] == phase]
        phases[phase] = {
            "n": len(rows),
            "mean_drs": _mean([_num(r["DRS"]) for r in rows]),
            "question_means": [_mean([_num(r[f"Q{i + 1}"]) for r in rows])
                               for i in range(len(config.DECISION_QUESTIONS))],
        }
    before = {r["Participant ID"]: _num(r["DRS"]) for r in survey if r["Phase"] == config.SURVEY_PHASES[0]}
    after = {r["Participant ID"]: _num(r["DRS"]) for r in survey if r["Phase"] == config.SURVEY_PHASES[-1]}
    paired = [after[p] - before[p] for p in after if p in before and after[p] is not None and before[p] is not None]
    survey_summary = {
        # a list keeps the order (the JSON keys of "phases" get sorted alphabetically)
        "phase_order": config.SURVEY_PHASES,
        "phases": phases, "questions": config.DECISION_QUESTIONS,
        "paired": len(paired), "mean_change": _mean(paired),
        "persist": Counter(r["Persist"] for r in survey if r["Persist"] in ("Yes", "No")),
        "practices": Counter(p for r in survey for p in r["Practices"].split("; ") if p),
    }

    hotspots = _public_hotspots()
    hotspot_summary = {"count": len(hotspots), "by_type": Counter(h["Type"] for h in hotspots),
                       "by_status": Counter(h["Status"] for h in hotspots)}

    # CSOD form answers from the Submit page ("About your day")
    readings = storage.read_submissions()

    def count(column, multi=False, order=None):
        c = Counter()
        for r in readings:
            for v in (r[column].split("; ") if multi else [r[column]]):
                if v:
                    c[v] += 1
        if order:
            return {k: c[k] for k in order if c[k]}
        return dict(c.most_common())

    answered = [r for r in readings if r["Sky"] or r["AQI source"] or r["Activities today"]]
    form_summary = {
        "answered": len(answered),
        "aqi_source": count("AQI source"),
        "sky": count("Sky", order=config.SKY_OPTIONS),
        "activities": count("Activities today", multi=True),
        "went_outside": count("Went outside", order=["Yes", "No"]),
        "study_place": count("Study place", order=config.STUDY_PLACES),
        "app_trigger": count("App trigger"),
        "poor_actions": count("Poor AQI actions", multi=True),
        "app_change": count("App change wanted"),
        "scales": [{"question": q, "mean": _mean([_num(r[col]) for r in readings])}
                   for col, q in config.FORM_SCALES],
    }

    # Spike check-ins (Phase 3 micro-survey)
    checkins = storage.read_table(storage.CHECKINS)
    checkin_summary = {
        "count": len(checkins),
        "spikes": len({r["Timestamp"][:10] for r in checkins}),
        "checked_app": Counter(r["Checked app (4h)"] for r in checkins if r["Checked app (4h)"]),
        "plan_changes": dict(Counter(c for r in checkins for c in r["Plan changes"].split("; ") if c).most_common()),
        "mean_anxiety": _mean([_num(r["Anxiety (1-5)"]) for r in checkins]),
        "anxiety_checked": _mean([_num(r["Anxiety (1-5)"]) for r in checkins if r["Checked app (4h)"] == "Yes"]),
        "anxiety_not_checked": _mean([_num(r["Anxiety (1-5)"]) for r in checkins if r["Checked app (4h)"] == "No"]),
    }

    return jsonify({"registration": registration, "diary": diary_summary,
                    "survey": survey_summary, "hotspots": hotspot_summary,
                    "form": form_summary, "checkins": checkin_summary})


@bp.get("/download/hotspots.csv")
def download_hotspots():
    rows = _public_hotspots()
    return _csv_response(list(rows[0].keys()) if rows else ["Timestamp"], rows, "hawa-hotspot-register.csv")


# ===========================================================================
# Admin: raw study files and hotspot verification
# ===========================================================================
def _csv_response(columns, rows, filename):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for r in rows:
        cells = []
        for c in columns:
            value = str(r.get(c, ""))
            if value[:1] in ("=", "+", "@") or (value[:1] == "-" and not value[1:2].isdigit()):
                value = "'" + value  # stop spreadsheet formula tricks
            cells.append(value)
        writer.writerow(cells)
    return Response("﻿" + output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@bp.get("/admin/download/<name>.csv")
def admin_download(name):
    if session.get("admin") is not True:
        return redirect(url_for("admin"))
    tables = {"participants": (storage.PARTICIPANT_COLUMNS, storage.read_participants()),
              "diary": (storage.DIARY["columns"], storage.read_table(storage.DIARY)),
              "survey": (storage.SURVEY["columns"], storage.read_table(storage.SURVEY)),
              "hotspots": (storage.HOTSPOTS["columns"], storage.read_table(storage.HOTSPOTS)),
              "checkins": (storage.CHECKINS["columns"], storage.read_table(storage.CHECKINS))}
    if name not in tables:
        return redirect(url_for("admin"))
    columns, rows = tables[name]
    return _csv_response(columns, rows, f"hawa-{name}.csv")
