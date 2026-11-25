"""
exposure.py
-----------
Personal Air Quality Exposure (PAQE) for the time-activity diary, following the
Standard Operating Protocol (SOP), Group A:

  * SOP item 7  - record time-activity patterns, estimate hourly PM2.5, give
                  personalized alerts
  * SOP part A  - hyper-local pollution data matched against the person's timeline
                  (current conditions, forecasts and hourly history)
  * SOP part B  - indoor / outdoor modifier (infiltration factor)
  * SOP part C  - breathing intensity (inhalation rate)

For each time block:
    Micro PM2.5 = Outdoor PM2.5 x Infiltration factor
    PAQE        = Hours x Micro PM2.5 x Breathing rate          (micrograms inhaled)

The SOP names the Google Air Quality API as the data source. That API is paid
(pay-as-you-go with a billing account), so this project uses free sources that
provide the same things: Open-Meteo (CAMS model) for hourly PM2.5 history and
forecasts for each zone's coordinates.
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

import airquality
import config
from storage import DATA_DIR

IST = timezone(timedelta(hours=5, minutes=30))
_pm_cache = {}            # (zone_id, "YYYY-MM-DD") -> (fetched time, {"YYYY-MM-DDTHH": pm25}, source)
_cache_lock = threading.Lock()

# The SOP's sample calculation (3-hour window), used on the pAQI page and in tests.
SOP_SAMPLE = [
    {"time": "8:00–9:00 AM", "location": "road_open", "activity": "commuting", "hours": 1, "outdoor": 50},
    {"time": "9:00–10:00 AM", "location": "work_filter", "activity": "indoor", "hours": 1, "outdoor": 40},
    {"time": "10:00–11:00 AM", "location": "outdoor_park", "activity": "exercise", "hours": 1, "outdoor": 30},
]


def today():
    return datetime.now(IST).date()


def hour_label(h):
    """6 -> '6 AM', 13 -> '1 PM', 24 -> '12 AM', 30 -> '6 AM' (next day)."""
    h %= 24
    suffix = "AM" if h < 12 else "PM"
    return f"{(h % 12) or 12} {suffix}"


def block_label(start, end):
    return f"{hour_label(start)}–{hour_label(end)}"


# ---------------------------------------------------------------------------
# Hourly PM2.5 for a zone and a date (plus the next morning, for overnight blocks)
#
# Sources, tried in this order:
#   1. Saved values (memory + data/pm_hourly.json), so finished days never need fetching again
#   2. Open-Meteo (CAMS model) for the zone's coordinates - history AND forecast
#   3. The official CPCB station via OpenAQ - the zone's own station (Patia, Lingaraj)
#      or the nearest one. Real measurements, but only for hours that have passed;
#      for today's later hours we use the same hour yesterday as an estimate.
# Open-Meteo's free plan has a daily limit per IP address, and PythonAnywhere's
# free accounts share IP addresses, so source 2 is sometimes blocked for a day.
# ---------------------------------------------------------------------------
PM_FILE = os.path.join(DATA_DIR, "pm_hourly.json")
_disk_loaded = {"done": False}
_open_meteo_blocked_until = {"t": 0.0}


def _load_disk_cache():
    if _disk_loaded["done"]:
        return
    _disk_loaded["done"] = True
    try:
        with open(PM_FILE, encoding="utf-8") as f:
            for key, item in json.load(f).items():
                zone_id, day = key.split("|")
                _pm_cache[(int(zone_id), day)] = (item["saved"], item["data"], item["source"])
    except Exception:
        pass


def _save_disk_cache():
    """Keep finished days on disk (at most 60 days back)."""
    oldest = (today() - timedelta(days=60)).isoformat()
    keep = {f"{z}|{d}": {"saved": t, "data": data, "source": src}
            for (z, d), (t, data, src) in _pm_cache.items() if oldest <= d < today().isoformat() and data}
    try:
        with open(PM_FILE, "w", encoding="utf-8") as f:
            json.dump(keep, f)
    except Exception:
        pass


def _from_open_meteo(zone, day):
    if time.time() < _open_meteo_blocked_until["t"]:
        raise RuntimeError("Open-Meteo is resting after a recent failure")
    try:
        response = requests.get(airquality.AIR_URL, timeout=20, params={
            "latitude": zone["lat"],
            "longitude": zone["lon"],
            "hourly": "pm2_5",
            "start_date": day.isoformat(),
            "end_date": (day + timedelta(days=1)).isoformat(),
            "timezone": "Asia/Kolkata",
        })
        response.raise_for_status()
    except Exception:
        _open_meteo_blocked_until["t"] = time.time() + 15 * 60  # don't hammer it; try again in 15 min
        raise
    hourly = response.json()["hourly"]
    return {t[:13]: v for t, v in zip(hourly["time"], hourly["pm2_5"]) if v is not None}


def _station_for_zone(zone):
    """The zone's own official station, else the nearest station that measures PM2.5."""
    locations = [loc for loc in airquality._list_locations()
                 if any((s.get("parameter") or {}).get("name") == "pm25" for s in loc.get("sensors", []))]
    if not locations:
        return None
    words = [w.lower() for w in (zone.get("station") or [])]
    own = [loc for loc in locations if any(w in str(loc.get("name", "")).lower() for w in words)]
    if own:
        return own[0]

    def distance(loc):
        c = loc.get("coordinates") or {}
        return ((c.get("latitude") or 0) - zone["lat"]) ** 2 + ((c.get("longitude") or 0) - zone["lon"]) ** 2
    return min(locations, key=distance)


def _station_hours(sensor_id, day_from, day_to):
    """{'YYYY-MM-DDTHH' (IST): pm25} of a station's hourly averages between two dates."""
    start = datetime(day_from.year, day_from.month, day_from.day, tzinfo=IST).astimezone(timezone.utc)
    end = datetime(day_to.year, day_to.month, day_to.day, tzinfo=IST).astimezone(timezone.utc)
    rows = airquality._openaq_get(f"/sensors/{sensor_id}/hours", {
        "datetime_from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "datetime_to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 200,
    })
    data = {}
    for r in rows:
        when = ((r.get("period") or {}).get("datetimeFrom") or {}).get("utc")
        value = r.get("value")
        if when and value is not None and value >= 0:
            hour = datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(IST)
            data[hour.strftime("%Y-%m-%dT%H")] = round(float(value), 1)
    return data


def _from_station(zone, day):
    if not os.environ.get("OPENAQ_API_KEY", "").strip():
        raise RuntimeError("no OpenAQ key")
    loc = _station_for_zone(zone)
    if not loc:
        raise RuntimeError("no station found")
    sensor = next(s["id"] for s in loc["sensors"] if (s.get("parameter") or {}).get("name") == "pm25")
    data = _station_hours(sensor, day - timedelta(days=1), day + timedelta(days=2))
    # Hours that haven't happened yet (today's alert): use the same hour one day earlier.
    estimated = False
    for h in range(0, 36):
        d = day + timedelta(days=h // 24)
        key = f"{d.isoformat()}T{h % 24:02d}"
        if key not in data:
            earlier = f"{(d - timedelta(days=1)).isoformat()}T{h % 24:02d}"
            if earlier in data:
                data[key] = data[earlier]
                estimated = True
    source = f"CPCB station via OpenAQ ({loc.get('name')})"
    if estimated:
        source += "; later hours estimated from the day before"
    return data, source


def hourly_pm25(zone_id, day):
    """Returns ({'YYYY-MM-DDTHH': pm25}, source text). Raises if no source works."""
    key = (zone_id, day.isoformat())
    with _cache_lock:
        _load_disk_cache()
        hit = _pm_cache.get(key)
        # A copy fetched after the diary day (which runs to 6 AM next day) was fully over holds
        # measured values only, so it never changes. Earlier copies may hold forecasts or
        # estimates, so they are refreshed every 30 minutes.
        after = day + timedelta(days=2)
        final = hit and hit[0] >= datetime(after.year, after.month, after.day, tzinfo=IST).timestamp()
        if hit and (final or time.time() - hit[0] < config.CACHE_SECONDS):
            return hit[1], hit[2]

    zone = next(z for z in config.ZONES if z["id"] == zone_id)
    try:
        data, source = _from_open_meteo(zone, day), "Open-Meteo CAMS hourly"
    except Exception as error:
        print("Open-Meteo hourly failed, trying the CPCB station:", type(error).__name__, str(error)[:120])
        try:
            data, source = _from_station(zone, day)
        except Exception as error2:
            print("Station hourly failed too:", type(error2).__name__, str(error2)[:120])
            if hit:  # an older saved copy is better than nothing
                return hit[1], hit[2]
            raise

    with _cache_lock:
        if len(_pm_cache) > 400:
            _pm_cache.clear()
        _pm_cache[key] = (time.time(), data, source)
        _save_disk_cache()
    return data, source


def _pm_for_hour(pm, day, hour):
    d = day + timedelta(days=hour // 24)
    return pm.get(f"{d.isoformat()}T{hour % 24:02d}")


# ---------------------------------------------------------------------------
# PAQE for one block and one day
# ---------------------------------------------------------------------------
def block_exposure(hours, outdoor, location, activity):
    factor = config.MICROENVIRONMENTS[location]["factor"]
    rate = config.ACTIVITIES[activity]["rate"]
    micro = outdoor * factor if outdoor is not None else None
    paqe = hours * micro * rate if micro is not None else None
    return factor, rate, micro, paqe


def validate_blocks(blocks):
    """Checks a diary day. Returns (clean blocks, error message or None)."""
    clean, used = [], set()
    if not isinstance(blocks, list) or not blocks:
        return None, "Add at least one time block."
    if len(blocks) > 12:
        return None, "Please use 12 time blocks or fewer."
    for b in blocks:
        try:
            start, end = int(b.get("start")), int(b.get("end"))
        except (TypeError, ValueError, AttributeError):
            return None, "Every block needs a start and end time."
        location, activity = b.get("location"), b.get("activity")
        if not (isinstance(location, str) and isinstance(activity, str)) \
                or location not in config.MICROENVIRONMENTS or activity not in config.ACTIVITIES:
            return None, "Please choose a location and an activity for every block."
        if not (0 <= start < 24 and start < end <= start + 24 and end <= 36):
            return None, f"The block starting at {hour_label(start)} has an invalid end time."
        hours = set(range(start, end))
        if hours & used:
            return None, f"The block {block_label(start, end)} overlaps another block."
        used |= hours
        clean.append({"start": start, "end": end, "location": location, "activity": activity})
    if len(used) > 24:
        return None, "The blocks add up to more than 24 hours."
    clean.sort(key=lambda b: b["start"])
    return clean, None


def compute_day(zone_id, day, blocks):
    """Returns {"rows": [...], "total": float, "alerts": [...], "source": "..."} for a diary day."""
    pm, source = hourly_pm25(zone_id, day)
    rows = []
    for b in blocks:
        hours = b["end"] - b["start"]
        values = [v for v in (_pm_for_hour(pm, day, h) for h in range(b["start"], b["end"])) if v is not None]
        outdoor = round(sum(values) / len(values), 1) if values else None
        factor, rate, micro, paqe = block_exposure(hours, outdoor, b["location"], b["activity"])
        rows.append({
            **b,
            "time": block_label(b["start"], b["end"]),
            "location_label": config.MICROENVIRONMENTS[b["location"]]["label"],
            "activity_label": config.ACTIVITIES[b["activity"]]["label"],
            "hours": hours,
            "outdoor": outdoor,
            "factor": factor,
            "rate": rate,
            "micro": round(micro, 1) if micro is not None else None,
            "paqe": round(paqe, 1) if paqe is not None else None,
        })
    total = round(sum(r["paqe"] for r in rows if r["paqe"] is not None), 1)
    return {"rows": rows, "total": total, "alerts": make_alerts(rows, pm, day, total), "source": source}


# ---------------------------------------------------------------------------
# Personalized alerts (SOP item 7)
# ---------------------------------------------------------------------------
def _cleanest_hour(pm, day, first=6, last=21):
    options = [(v, h) for h in range(first, last + 1)
               if (v := _pm_for_hour(pm, day, h)) is not None]
    return min(options) if options else (None, None)


def make_alerts(rows, pm, day, total):
    alerts = []
    level = config.PM25_ALERT_LEVEL
    measured = [r for r in rows if r["paqe"] is not None]
    if not measured or total <= 0:
        return ["PM2.5 data isn't available for this day yet, so no alerts could be made."]

    biggest = max(measured, key=lambda r: r["paqe"])
    alerts.append(f"Your biggest exposure was {biggest['time']} ({biggest['activity_label'].lower()}, "
                  f"{biggest['location_label'].split(':')[0].lower()}): "
                  f"{round(100 * biggest['paqe'] / total)}% of your day’s PAQE.")

    clean_value, clean_hour = _cleanest_hour(pm, day)
    for r in measured:
        if r["outdoor"] is not None and r["outdoor"] > level and r["factor"] >= 0.8:
            if r["location"].startswith("home") or r["location"].startswith("work"):
                tip = "keep windows closed or run an air purifier at these times"
            else:
                tip = "wear an N95 mask or move this activity indoors"
                if clean_hour is not None and clean_value < r["outdoor"] * 0.7:
                    tip = (f"the cleanest time was around {hour_label(clean_hour)} "
                           f"({round(clean_value)} µg/m³), or wear an N95 mask")
            alerts.append(f"⚠ Outdoor PM2.5 averaged {round(r['outdoor'])} µg/m³ during {r['time']} "
                          f"({r['activity_label'].lower()}), above the CPCB standard of {level} µg/m³: {tip}.")

    # Outdoor exercise at a dirtier time than necessary
    for r in measured:
        if r["activity"] in ("exercise", "walking") and r["factor"] >= 1.0 and clean_hour is not None:
            if r["outdoor"] and clean_value < r["outdoor"] * 0.75:
                alerts.append(f"Tip: your {r['activity_label'].lower()} at {r['time']} would inhale about "
                              f"{round(100 * (1 - clean_value / r['outdoor']))}% less PM2.5 around "
                              f"{hour_label(clean_hour)}.")
                break

    if len(alerts) == 1:
        alerts.append(f"Good news: outdoor PM2.5 stayed below {level} µg/m³ during all your outdoor time.")
    return alerts[:5]


def forecast_alert(zone_id, blocks):
    """Today's alert: the person's usual day matched against today's hourly forecast."""
    result = compute_day(zone_id, today(), blocks)
    result["date"] = today().isoformat()
    return result


def sop_sample():
    """The SOP's worked example. Must give 60 + 4 + 75 = 139."""
    rows = []
    for s in SOP_SAMPLE:
        factor, rate, micro, paqe = block_exposure(s["hours"], s["outdoor"], s["location"], s["activity"])
        rows.append({**s, "location_label": config.MICROENVIRONMENTS[s["location"]]["label"],
                     "activity_label": config.ACTIVITIES[s["activity"]]["label"],
                     "factor": factor, "rate": rate, "micro": micro, "paqe": paqe})
    return rows, round(sum(r["paqe"] for r in rows), 1)
