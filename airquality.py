"""
airquality.py
-------------
1. Converts PM2.5 / PM10 concentrations into an Indian (CPCB) AQI number.
2. Fetches live air quality + temperature for every zone from Open-Meteo
   (free, no API key).
3. Fetches readings from the OFFICIAL CPCB/OSPCB monitoring stations in
   Bhubaneswar through OpenAQ (free API key needed, see config.py).
   OpenAQ is a non-profit that copies government station data worldwide.
   (We don't use data.gov.in directly because it blocks servers outside India,
   such as PythonAnywhere.)
Everything is cached for 30 minutes.

Two kinds of "official-style" data, explained:
  - Open-Meteo = the CAMS computer model (satellites + weather models). Covers
    every zone, but one value per ~40 km grid square, so all zones look the same.
  - CPCB station = a real monitor on the ground. Very accurate, but Bhubaneswar
    only has two (Patia and Lingaraj), so only zones 3 and 5 get one.

Check your setup by running this file directly:
    python airquality.py
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

import config
from storage import DATA_DIR

CACHE_FILE = os.path.join(DATA_DIR, "live_cache.json")
IST = timezone(timedelta(hours=5, minutes=30))

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
OPENAQ_URL = "https://api.openaq.org/v3"

# ---------------------------------------------------------------------------
# CPCB AQI breakpoints: (concentration low, concentration high, AQI low, AQI high)
# PM values in micrograms per cubic metre (ug/m3), 24-hour average.
# ---------------------------------------------------------------------------
PM25_BREAKPOINTS = [
    (0, 30, 0, 50),        # Good
    (30, 60, 50, 100),     # Satisfactory
    (60, 90, 100, 200),    # Moderate
    (90, 120, 200, 300),   # Poor
    (120, 250, 300, 400),  # Very Poor
    (250, 380, 400, 500),  # Severe
]
PM10_BREAKPOINTS = [
    (0, 50, 0, 50),
    (50, 100, 50, 100),
    (100, 250, 100, 200),
    (250, 350, 200, 300),
    (350, 430, 300, 400),
    (430, 510, 400, 500),
]


def _sub_index(conc, breakpoints):
    """Straight-line interpolation inside the right breakpoint band."""
    if conc is None:
        return None
    conc = max(0.0, float(conc))
    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        if conc <= c_hi:
            return round(i_lo + (i_hi - i_lo) * (conc - c_lo) / (c_hi - c_lo))
    return 500  # above the top band


def aqi_from_pm(pm25=None, pm10=None):
    """CPCB AQI = the worst (highest) of the PM2.5 and PM10 sub-indices."""
    values = [v for v in (_sub_index(pm25, PM25_BREAKPOINTS),
                          _sub_index(pm10, PM10_BREAKPOINTS)) if v is not None]
    return max(values) if values else None


def band_name(aqi):
    if aqi is None:
        return None
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Satisfactory"
    if aqi <= 200:
        return "Moderate"
    if aqi <= 300:
        return "Poor"
    if aqi <= 400:
        return "Very Poor"
    return "Severe"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _average(values):
    nums = [v for v in values if v is not None]
    return round(sum(nums) / len(nums), 1) if nums else None


def _as_list(payload):
    """Open-Meteo returns a list for several locations, a dict for one."""
    return payload if isinstance(payload, list) else [payload]


def _number(text):
    """'42.5' -> 42.5, 'NA' / '' / None -> None (stations often send 'NA')."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 1) Open-Meteo model data (every zone)
# ---------------------------------------------------------------------------
_last_weather = {}  # the last temperatures Open-Meteo gave us (used if a later request fails)


def _fetch_from_open_meteo():
    """Ask Open-Meteo for all 5 zones in ONE request. Raises an error on failure."""
    lats = ",".join(str(z["lat"]) for z in config.ZONES)
    lons = ",".join(str(z["lon"]) for z in config.ZONES)

    air = requests.get(AIR_URL, timeout=15, params={
        "latitude": lats,
        "longitude": lons,
        "current": "pm2_5,pm10",
        "hourly": "pm2_5,pm10",
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "Asia/Kolkata",
    })
    air.raise_for_status()
    air_list = _as_list(air.json())

    # Temperature is a "nice to have": if this request fails (Open-Meteo's daily limit on a
    # shared server) we reuse the last temperatures we got, for up to 12 hours.
    try:
        weather = requests.get(WEATHER_URL, timeout=15, params={
            "latitude": lats,
            "longitude": lons,
            "current": "temperature_2m,relative_humidity_2m",
            "timezone": "Asia/Kolkata",
        })
        weather.raise_for_status()
        weather_list = _as_list(weather.json())
        _last_weather.update({"list": weather_list, "epoch": time.time()})
    except Exception as error:
        print("Open-Meteo temperature failed:", type(error).__name__, str(error)[:120])
        if _last_weather.get("list") and time.time() - _last_weather["epoch"] < 12 * 3600:
            weather_list = _last_weather["list"]
        else:
            weather_list = [{}] * len(config.ZONES)

    zones = []
    for zone, a, w in zip(config.ZONES, air_list, weather_list):
        current = a.get("current", {})
        hourly = a.get("hourly", {})
        now_label = current.get("time", "")

        # Keep the last 24 hourly values up to "now" (times are "2026-11-06T14:00").
        idx = [i for i, t in enumerate(hourly.get("time", [])) if t <= now_label][-24:]
        times = [hourly["time"][i][11:16] for i in idx]  # just "HH:MM"
        pm25_series = [hourly["pm2_5"][i] for i in idx]
        pm10_series = [hourly["pm10"][i] for i in idx]

        pm25_24h = _average(pm25_series)
        pm10_24h = _average(pm10_series)
        aqi = aqi_from_pm(pm25_24h, pm10_24h)  # CPCB uses 24-hour averages

        zones.append({
            "zone_id": zone["id"],
            "aqi": aqi,
            "band": band_name(aqi),
            "pm25_now": current.get("pm2_5"),
            "pm10_now": current.get("pm10"),
            "pm25_24h": pm25_24h,
            "pm10_24h": pm10_24h,
            "temp": (w.get("current") or {}).get("temperature_2m"),
            "humidity": (w.get("current") or {}).get("relative_humidity_2m"),
            "hourly": {"time": times, "pm25": pm25_series},
            "station": None,  # filled in below if the zone has an official station
        })

    now = datetime.now(IST)
    return {
        "zones": zones,
        "fetched_at": now.strftime("%Y-%m-%d %H:%M IST"),
        "fetched_epoch": time.time(),
    }


# ---------------------------------------------------------------------------
# 2) Official CPCB / OSPCB stations through OpenAQ (zones 3 and 5)
# ---------------------------------------------------------------------------
def _openaq_get(path, params=None):
    """Call the OpenAQ API. The key goes in a header, so it never appears in URLs or errors."""
    key = os.environ.get("OPENAQ_API_KEY", "").strip()
    # Short timeout: if OpenAQ is slow, the page shouldn't hang waiting for it.
    response = requests.get(OPENAQ_URL + path, params=params, timeout=12,
                            headers={"X-API-Key": key, "Accept": "application/json"})
    response.raise_for_status()
    return response.json().get("results", [])


def _list_locations():
    """Every OpenAQ monitoring location inside the Bhubaneswar box from config.py."""
    return _openaq_get("/locations", {"bbox": config.STATION_BBOX, "limit": 100})


def _parse_time(text):
    """'2026-11-13T03:00:00Z' -> a datetime (or None)."""
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def _latest_pm(location):
    """
    Latest PM2.5 and PM10 for one location.
    OpenAQ lists each location's sensors (one per pollutant); /latest gives the
    newest value per sensor, so we match sensor ids to know which is which.
    Readings older than STATION_MAX_AGE_HOURS are ignored (station offline).
    Returns (pm25, pm10, "YYYY-MM-DD HH:MM" in IST or None, temperature in °C or None).
    Many CPCB stations also measure air temperature; we use it when Open-Meteo's
    temperature isn't available.
    """
    sensor_param = {}
    for s in location.get("sensors", []):
        sensor_param[s.get("id")] = (s.get("parameter") or {}).get("name")

    now = datetime.now(timezone.utc)
    values, newest = {}, None
    for m in _openaq_get(f"/locations/{location['id']}/latest"):
        param = sensor_param.get(m.get("sensorsId"))
        value = _number(m.get("value"))
        when = _parse_time((m.get("datetime") or {}).get("utc"))
        if value is None or when is None or now - when > timedelta(hours=config.STATION_MAX_AGE_HOURS):
            continue  # missing, or too old to call "live"
        if param == "temperature" and -5 <= value <= 55:
            values["temperature"] = value
        elif param in ("pm25", "pm10") and value >= 0:
            values[param] = value
            newest = max(newest, when) if newest else when

    updated = newest.astimezone(IST).strftime("%Y-%m-%d %H:%M IST") if newest else None
    return values.get("pm25"), values.get("pm10"), updated, values.get("temperature")


def _fetch_stations():
    """Returns (stations per zone, list of all location names in the box). Raises on failure."""
    locations = _list_locations()
    names = sorted({str(loc.get("name") or "?") for loc in locations})

    result = {}
    for zone in config.ZONES:
        words = [w.lower() for w in (zone.get("station") or [])]
        if not words:
            continue
        # All locations whose name contains one of the zone's station words.
        # Prefer reference monitors (isMonitor) and the most recently updated.
        candidates = [loc for loc in locations
                      if any(w in str(loc.get("name") or "").lower() for w in words)]
        candidates.sort(key=lambda loc: (bool(loc.get("isMonitor")),
                                         str((loc.get("datetimeLast") or {}).get("utc") or "")),
                        reverse=True)
        for loc in candidates:
            pm25, pm10, updated, temp = _latest_pm(loc)
            aqi = aqi_from_pm(pm25, pm10)
            if aqi is None:
                continue  # offline or no PM sensors: try the next candidate
            result[zone["id"]] = {
                "name": str(loc.get("name")),
                "aqi": aqi,
                "band": band_name(aqi),
                "pm25": pm25,
                "pm10": pm10,
                "temp": temp,
                "updated": updated,
                "stale": False,
            }
            break
    return result, names


def _get_stations(previous):
    """
    Fetch station data, but never let it break the page.
    Returns (stations per zone, status, station names seen).
    status: "ok", "not_found", "no_key" or "error".
    """
    if not os.environ.get("OPENAQ_API_KEY", "").strip():
        return {}, "no_key", []
    try:
        by_zone, seen = _fetch_stations()
        return by_zone, ("ok" if by_zone else "not_found"), seen
    except Exception as error:
        print("OpenAQ request failed:", type(error).__name__, str(error)[:300])
        # Re-use the last station values we had, marked as old.
        old = {}
        for z in (previous or {}).get("zones", []):
            if z.get("station"):
                old[z["zone_id"]] = {**z["station"], "stale": True}
        return old, "error", (previous or {}).get("stations_seen", [])


# ---------------------------------------------------------------------------
# Cache (memory + data/live_cache.json so it survives restarts)
# ---------------------------------------------------------------------------
_cache = {"data": None}
_fetch_lock = threading.Lock()


def _load_cache_file():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache_file(data):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass  # caching to disk is optional


def _fill_missing_temperatures(fresh, cached):
    """
    If Open-Meteo gave no temperature: use the CPCB stations' thermometer (the zone's own
    station, else the city average of the stations), else the last temperature we had
    within 12 hours. Temperature barely differs across the city, so this is fine.
    """
    station_temps = [z["station"]["temp"] for z in fresh["zones"]
                     if z.get("station") and z["station"].get("temp") is not None]
    city = round(sum(station_temps) / len(station_temps), 1) if station_temps else None
    old = {}
    if cached and time.time() - cached.get("fetched_epoch", 0) < 12 * 3600:
        old = {z["zone_id"]: z.get("temp") for z in cached.get("zones", [])}
    for z in fresh["zones"]:
        if z.get("temp") is None:
            own = (z.get("station") or {}).get("temp")
            z["temp"] = own if own is not None else city if city is not None else old.get(z["zone_id"])


def get_live_data():
    """
    Returns live data for all zones plus a "status":
      "live"        -> fresh (or cached less than 30 min ago)
      "stale"       -> Open-Meteo failed, showing the last saved value
      "unavailable" -> Open-Meteo failed and we have never saved anything
    Each zone has a "station" entry: official station data, or None.
    """
    with _fetch_lock:
        if _cache["data"] is None:
            _cache["data"] = _load_cache_file()  # survive server restarts

        cached = _cache["data"]
        age = time.time() - cached["fetched_epoch"] if cached else None
        # A cache saved without the OpenAQ key (e.g. from a console test) has no
        # station data: don't reuse it once the key is available.
        key_added = (cached and cached.get("station_status") == "no_key"
                     and os.environ.get("OPENAQ_API_KEY", "").strip())
        if cached and age < config.CACHE_SECONDS and not key_added:
            return {**cached, "status": cached.get("model_status", "live")}

        try:
            fresh = _fetch_from_open_meteo()
            fresh["model_status"] = "live"
        except Exception as error:
            # Open-Meteo's free plan has a daily limit per IP address, and free
            # PythonAnywhere accounts share IP addresses, so this does happen.
            print("Open-Meteo request failed:", str(error)[:200])
            if not cached:
                return {"zones": [], "fetched_at": None, "status": "unavailable",
                        "station_status": "error", "stations_seen": []}
            # Keep the last model values (marked as old) but still refresh the official stations,
            # and try Open-Meteo again in 15 minutes rather than on every page visit.
            fresh = json.loads(json.dumps(cached))
            fresh["fetched_epoch"] = time.time() - config.CACHE_SECONDS + 15 * 60
            fresh["model_status"] = "stale"

        by_zone, station_status, seen = _get_stations(cached)
        for z in fresh["zones"]:
            z["station"] = by_zone.get(z["zone_id"])
        fresh["station_status"] = station_status
        fresh["stations_seen"] = seen
        _fill_missing_temperatures(fresh, cached)

        _cache["data"] = fresh
        _save_cache_file(fresh)
        return {**fresh, "status": fresh["model_status"]}


def reference_for_zone(zone_id):
    """
    The value a community reading is compared with:
    the official station if the zone has one, otherwise the model.
    Returns (aqi or None, "CPCB station" / "Model").
    """
    for z in get_live_data()["zones"]:
        if z["zone_id"] == zone_id:
            if z.get("station") and z["station"].get("aqi") is not None:
                return z["station"]["aqi"], "CPCB station"
            return z["aqi"], "Model"
    return None, ""


# ---------------------------------------------------------------------------
# Run "python airquality.py" to check that your OpenAQ key works and to see
# which stations OpenAQ has around Bhubaneswar.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not os.environ.get("OPENAQ_API_KEY", "").strip():
        print("OPENAQ_API_KEY is not set. Set it first, then run this again.")
        raise SystemExit(1)
    print("Asking OpenAQ for stations in the Bhubaneswar box", config.STATION_BBOX, "...")
    try:
        locations = _list_locations()
        print(f"\n{len(locations)} location(s) found:")
        for loc in locations:
            params = sorted({(s.get("parameter") or {}).get("name") for s in loc.get("sensors", [])} - {None})
            last = ((loc.get("datetimeLast") or {}).get("local") or "?")[:16]
            kind = "monitor" if loc.get("isMonitor") else "low-cost sensor"
            print(f"  - {loc.get('name')} | {kind} | last data {last} | {', '.join(params)}")
        by_zone, names = _fetch_stations()
    except Exception as error:
        print("FAILED:", type(error).__name__, "-", str(error)[:300])
        print("The site still works: every zone falls back to the Open-Meteo model.")
        raise SystemExit(1)
    print("\nWhat the site will show:")
    for zone in config.ZONES:
        s = by_zone.get(zone["id"])
        if s:
            print(f"  Zone {zone['id']} {zone['name']}: {s['name']} -> AQI {s['aqi']} "
                  f"(PM2.5 {s['pm25']}, PM10 {s['pm10']}, updated {s['updated']})")
        elif zone.get("station"):
            print(f"  Zone {zone['id']} {zone['name']}: station not found or offline")
        else:
            print(f"  Zone {zone['id']} {zone['name']}: no official station (uses the model)")
