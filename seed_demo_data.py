"""
seed_demo_data.py
-----------------
Fills every data file with a SAMPLE dataset that follows the Standard Operating
Protocol, so the site, the Data page and the admin panel can be shown working
before real participants join:

  * 30 participants (the SOP registration target) across the 5 zones, each with
    consent, an anonymous ID, age group, gender, occupation and workplace
  * a "before alerts" decision-making survey on the day each person registers
  * a 14-day time-activity diary (a few missed days, two people who drop out)
    with hourly outdoor PM2.5, infiltration factors, breathing rates and PAQE.
    After the first week, people who respond to the alerts change their day
    (windows closed / purifier at night, exercise moved indoors, closed transport)
  * an "after alerts" survey on day 14 with the persistence question
  * a hotspot register with verified, unconfirmed and newly reported entries
  * community readings from the participants who own a monitor

The air values are REAL: the script downloads Bhubaneswar's hourly PM2.5, PM10
and temperature for the study period from Open-Meteo. Community readings vary a
little around them by zone, like real low-cost monitors would.

    python seed_demo_data.py            -> load the sample data (only if the files are empty)
    python seed_demo_data.py --force    -> replace whatever is there with sample data
    python seed_demo_data.py --clear    -> empty every file (do this before real collection)

While the sample data is loaded, the admin panel says so (the file data/DEMO_DATA
marks it) and has a button to clear it.
"""

import math
import os
import random
import sys
from datetime import date, datetime, time, timedelta, timezone

import requests

import airquality
import config
import storage

IST = timezone(timedelta(hours=5, minutes=30))
STUDY_DAYS = config.STUDY_DAYS              # 14
PARTICIPANTS = config.REGISTRATION_TARGET   # 30
DROPOUTS = 2                                # people who stop logging after the first week
MARKER_FILE = os.path.join(storage.DATA_DIR, "DEMO_DATA")

# People per zone (adds up to 30)
ZONE_PEOPLE = {1: 6, 2: 6, 3: 7, 4: 5, 5: 6}
# How each zone's street-level air usually compares with the city-wide model (1.0 = the same)
ZONE_FACTOR = {1: 1.15, 2: 1.10, 3: 1.00, 4: 0.82, 5: 1.05}
NOISE = 0.08            # low-cost monitors differ by about ±8%
Z_HAS_STATION = {z["id"]: bool(z.get("station")) for z in config.ZONES}

NOTES = {
    1: ["Truck queue near the estate gate", "Chemical smell after 8 pm", "Black smoke from a chimney",
        "Dust from trucks on the service road", "Better after the rain", "Haze over the warehouses"],
    2: ["Traffic jam at Master Canteen square", "Bus exhaust at the stop", "Smoke from autos in the queue",
        "Diesel smell near the station", "Signal stuck, long queue", "Less traffic on Sunday"],
    3: ["Construction dust near Infocity", "New building work next to office", "Road digging on the main road",
        "Cement trucks all morning", "Wind cleared the dust today", "Water sprinkling at the site helped"],
    4: ["Morning walk near the zoo", "Very green, easy to breathe", "Some leaf burning on the roadside",
        "Air feels clean today", "Light haze over the forest", "Mist in the morning"],
    5: ["Garbage burning near the market", "Incense and cooking smoke in the lanes", "Crowd near Lingaraj",
        "Narrow lane, no breeze", "Firecrackers last night", "Smoke from a roadside stall"],
}
ACTIVITY_WEIGHTS = {"At home": 3, "Commuting": 4, "Office / indoors": 2, "Outdoor work": 2, "Exercise": 2, "Other": 1}

HOTSPOTS = [
    # zone, type, landmark, description, study day reported
    (3, "Construction dust", "Infocity main road, near the flyover work", "Dust cloud from building site, 8–10 AM", 2),
    (1, "Heavy truck movement", "Mancheswar industrial estate gate", "Long queue of trucks every evening", 3),
    (2, "Road dust resuspension", "Master Canteen square", "Dust kicked up by buses near the stop", 4),
    (1, "Industrial activity", "Rasulgarh, behind the warehouses", "Grey smoke from a chimney in the morning", 5),
    (5, "Roadside waste burning", "Lane behind the Lingaraj market", "Garbage burnt after 7 PM", 6),
    (4, "Roadside waste burning", "Nandankanan road, near the bus stop", "Leaf burning by the roadside", 7),
    (3, "Construction dust", "Patia, near KIIT square", "Uncovered sand piles beside the road", 9),
    (2, "Heavy truck movement", "Station road, near the goods yard", "Trucks idling with engines on", 10),
    (5, "Road dust resuspension", "Old Town, Bindu Sagar road", "Broken road surface, dust from autos", 12),
    (1, "Roadside waste burning", "Mancheswar, near the railway crossing", "Plastic waste burnt in the open", 13),
    (3, "Construction dust", "Chandrasekharpur, new apartment site", "Grinding and cutting without water spray", 14),
]
VERIFY_NOTES = {
    "Construction dust": ["Field observation from the footpath on 2 days", "Photo taken from the public road"],
    "Heavy truck movement": ["Counted about 40 trucks between 6 and 7 PM", "Observed on 3 evenings"],
    "Road dust resuspension": ["Repeat visit; Lingraj/Patia station PM2.5 also high that morning",
                               "Seen again on a dry, windy afternoon"],
    "Roadside waste burning": ["Seen and reported to the BMC helpline", "Seen twice; reported to the ward office"],
    "Industrial activity": ["Location recorded; no cause attributed", "Not seen on 2 repeat visits"],
}


# ---------------------------------------------------------------------------
# Real air for Bhubaneswar over the study period
# ---------------------------------------------------------------------------
def _avg(values):
    nums = [v for v in values if v is not None]
    return sum(nums) / len(nums) if nums else None


def fetch_real_history(days):
    """Hourly history {"2026-11-13T09": {"aqi_now", "aqi_24h", "pm25", "temp"}} from Open-Meteo."""
    lat, lon = config.ZONES[2]["lat"], config.ZONES[2]["lon"]
    air = requests.get(airquality.AIR_URL, timeout=30, params={
        "latitude": lat, "longitude": lon, "hourly": "pm2_5,pm10",
        "past_days": days, "forecast_days": 2, "timezone": "Asia/Kolkata",
    })
    air.raise_for_status()
    h = air.json()["hourly"]

    temps = {}
    try:
        weather = requests.get(airquality.WEATHER_URL, timeout=30, params={
            "latitude": lat, "longitude": lon, "hourly": "temperature_2m",
            "past_days": days, "forecast_days": 2, "timezone": "Asia/Kolkata",
        })
        weather.raise_for_status()
        w = weather.json()["hourly"]
        temps = {t[:13]: v for t, v in zip(w["time"], w["temperature_2m"])}
    except Exception:
        pass

    history = {}
    for i, t in enumerate(h["time"]):
        pm25, pm10 = h["pm2_5"][i], h["pm10"][i]
        if pm25 is None:
            continue
        window = slice(max(0, i - 23), i + 1)
        history[t[:13]] = {
            "aqi_now": airquality.aqi_from_pm(pm25, pm10),
            "aqi_24h": airquality.aqi_from_pm(_avg(h["pm2_5"][window]), _avg(h["pm10"][window])),
            "pm25": pm25,
            "temp": temps.get(t[:13]),
        }
    return history


def station_ratios():
    """How the official stations compare with the model right now (e.g. 57/64). Default 1.0."""
    ratios = {}
    try:
        for z in airquality.get_live_data()["zones"]:
            if z.get("station") and z["station"].get("aqi") and z.get("aqi"):
                ratios[z["zone_id"]] = max(0.7, min(1.4, z["station"]["aqi"] / z["aqi"]))
    except Exception:
        pass
    return ratios


def pm25_from_aqi(aqi):
    """Rough inverse of the CPCB PM2.5 scale (same breakpoints as airquality.py)."""
    bands = [(0, 30, 0, 50), (30, 60, 50, 100), (60, 90, 100, 200),
             (90, 120, 200, 300), (120, 250, 300, 400), (250, 380, 400, 500)]
    for c_lo, c_hi, i_lo, i_hi in bands:
        if aqi <= i_hi:
            return c_lo + (c_hi - c_lo) * (aqi - i_lo) / (i_hi - i_lo)
    return 380


def at(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), IST)


def stamp(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def weighted_choice(weights):
    return random.choices(list(weights.keys()), weights=list(weights.values()))[0]


# ---------------------------------------------------------------------------
# Participants (SOP items 1-6)
# ---------------------------------------------------------------------------
WORK_FOR = {
    "Student": "Indoor, windows open", "Office / IT": "Indoor, AC with air filter",
    "Outdoor work (construction, vendor, driver)": "Outdoors", "Shop / market": "Indoor, windows open",
    "Healthcare": "Indoor, AC", "Home-maker": "Works / studies from home", "Retired": "Works / studies from home",
    "Other": "Indoor, windows open",
}
WORK_BLOCK = {"Indoor, AC with air filter": ("work_filter", "indoor"), "Indoor, AC": ("work_filter", "indoor"),
              "Indoor, windows open": ("work_open", "indoor"), "Outdoors": ("road_open", "walking"),
              "Works / studies from home": ("home_open", "indoor")}


def make_people(day1):
    people, used = [], set()
    for zone_id, count in ZONE_PEOPLE.items():
        for _ in range(count):
            while True:
                pid = f"BBSR-Z{zone_id}-{random.randint(100, 999)}"
                if pid not in used:
                    used.add(pid)
                    break
            occupation = random.choices(config.OCCUPATIONS, weights=[8, 6, 3, 3, 2, 3, 2, 1])[0]
            age = random.choices(config.AGE_GROUPS, weights=[9, 6, 4, 3, 2])[0]
            if occupation == "Retired":
                age = "60+"
            elif occupation == "Student" and age in ("45–59", "60+"):
                age = "18–24"
            # Registration over the 3 days before the diary starts
            created = at(day1 - timedelta(days=random.randint(0, 2)), random.randint(9, 20), random.randint(0, 59))
            people.append({
                "id": pid, "zone": zone_id, "created": created,
                "age": age, "gender": random.choices(config.GENDERS, weights=[46, 50, 1, 3])[0],
                "occupation": occupation, "workplace": WORK_FOR[occupation],
                "purifier": random.random() < 0.15, "car": random.random() < 0.25,
                "exercises": random.random() < 0.45,
                "responsive": random.random(),    # how strongly they react to the alerts
                "adherence": random.uniform(0.82, 1.0),
                "monitor": random.random() < 0.6,  # owns a low-cost monitor / uses an AQI app
            })
    people.sort(key=lambda p: p["created"])
    for p in random.sample(people, DROPOUTS):
        p["dropout_after"] = random.randint(5, 8)
    return people


def participant_rows(people):
    return [{"Participant ID": p["id"], "Zone": p["zone"], "Created": stamp(p["created"]), "City": config.CITY,
             "Age group": p["age"], "Gender": p["gender"], "Occupation": p["occupation"],
             "Workplace": p["workplace"], "Consent": "Yes " + stamp(p["created"])} for p in people]


# ---------------------------------------------------------------------------
# Diary (SOP item 7): the SOP standard day, adjusted per person
# ---------------------------------------------------------------------------
def person_day(p, changed, weekend):
    work_loc, work_act = WORK_BLOCK[p["workplace"]]
    closes_windows = p["purifier"] or (changed and p["responsive"] > 0.35)
    night = "home_closed" if closes_windows else "home_open"
    commute = "road_closed" if (p["car"] or (changed and p["responsive"] > 0.75)) else "road_open"
    if p["exercises"]:
        evening = ("outdoor_park", "exercise")
        if changed and p["responsive"] > 0.5:
            evening = ("home_closed" if closes_windows else "home_open", "exercise")  # moved indoors
    else:
        evening = random.choice([("outdoor_park", "walking"), ("home_open", "indoor"), ("road_open", "walking")])

    if weekend or work_loc == "home_open":
        blocks = [
            {"start": 7, "end": 10, "location": "home_open", "activity": "indoor"},
            {"start": 10, "end": 12, "location": "road_open", "activity": "walking"},
            {"start": 12, "end": 18, "location": "home_open", "activity": "indoor"},
        ]
    else:
        blocks = [
            {"start": 6, "end": 8, "location": "home_open", "activity": "indoor"},
            {"start": 8, "end": 9, "location": commute, "activity": "commuting"},
            {"start": 9, "end": 17, "location": work_loc, "activity": work_act},
            {"start": 17, "end": 18, "location": commute, "activity": "commuting"},
        ]
    blocks.append({"start": 18, "end": 20, "location": evening[0], "activity": evening[1]})
    blocks.append({"start": 20, "end": 30, "location": night, "activity": "sleeping"})
    if weekend or work_loc == "home_open":
        blocks.insert(0, {"start": 6, "end": 7, "location": "home_open", "activity": "indoor"})
    return blocks


def hour_text(h):
    return f"{h % 24:02d}:00" + ("+1" if h >= 24 else "")


def diary_rows(p, days, history, alert_day):
    rows = []
    first = days[0]
    for day in days:
        changed = (day - first).days + 1 >= alert_day
        for b in person_day(p, changed, day.weekday() == 6):
            values = []
            for h in range(b["start"], b["end"]):
                key = (day + timedelta(days=h // 24)).isoformat() + f"T{h % 24:02d}"
                if key in history:
                    values.append(history[key]["pm25"])
            if not values:
                continue
            outdoor = round(sum(values) / len(values), 1)
            factor = config.MICROENVIRONMENTS[b["location"]]["factor"]
            rate = config.ACTIVITIES[b["activity"]]["rate"]
            hours = b["end"] - b["start"]
            rows.append({
                "Date": day.isoformat(), "Participant ID": p["id"], "Day": (day - first).days + 1,
                "Start": hour_text(b["start"]), "End": hour_text(b["end"]),
                "Location": b["location"], "Activity": b["activity"], "Hours": hours,
                "Outdoor PM2.5": outdoor, "Infiltration": factor, "Breathing rate": rate,
                "Micro PM2.5": round(outdoor * factor, 1), "PAQE (ug)": round(hours * outdoor * factor * rate, 1),
                "Source": "Open-Meteo CAMS hourly",
            })
    return rows


# ---------------------------------------------------------------------------
# Surveys (SOP items 8 and 10)
# ---------------------------------------------------------------------------
def survey_rows(p, finished, after_time):
    m = len(config.DECISION_QUESTIONS)
    before = [max(1, min(5, round(random.gauss(2.3, 0.8)))) for _ in range(m)]
    practices = random.sample(["Mask", "Choice of transport"], random.randint(0, 1))
    if p["purifier"]:
        practices.append("Air purifier")
    rows = [{"Timestamp": stamp(p["created"] + timedelta(minutes=random.randint(8, 40))), "Participant ID": p["id"],
             "Phase": config.SURVEY_PHASES[0], **{f"Q{i + 1}": s for i, s in enumerate(before)},
             "DRS": round(sum(before) / m, 2), "Practices": "; ".join(sorted(practices)), "Persist": ""}]
    if finished:
        gain = 0.3 + 1.6 * p["responsive"]     # responsive people change more
        after = [max(1, min(5, round(s + random.gauss(gain, 0.6)))) for s in before]
        more = set(practices) | {"Choosing when to ventilate the home"} if p["responsive"] > 0.35 else set(practices)
        if p["responsive"] > 0.6:
            more |= {"Mask"}
        persist = "Yes" if random.random() < 0.35 + 0.6 * p["responsive"] else "No"
        rows.append({"Timestamp": stamp(after_time), "Participant ID": p["id"], "Phase": config.SURVEY_PHASES[-1],
                     **{f"Q{i + 1}": s for i, s in enumerate(after)}, "DRS": round(sum(after) / m, 2),
                     "Practices": "; ".join(sorted(more)), "Persist": persist})
    return rows


# ---------------------------------------------------------------------------
# Community readings
# ---------------------------------------------------------------------------
def feel_for(aqi, zone_id):
    if aqi < 60:
        return random.choice(["Fresh", "Normal", "Normal"])
    if aqi < 110:
        return random.choice(["Normal", "Normal", "Dusty"] + (["Smoky"] if zone_id in (2, 5) else []))
    if aqi < 200:
        return random.choice(["Dusty", "Smoky"] + (["Chemical smell"] if zone_id == 1 else []))
    return random.choice(["Smoky", "Hard to breathe"] + (["Chemical smell"] if zone_id == 1 else []))


def reading_rows(people, first_day, now, history, ratios):
    rows = []
    for p in people:
        if not p["monitor"]:
            continue
        keen = random.uniform(0.35, 0.8)
        day = max(first_day, p["created"].date())
        while day <= now.date():
            if random.random() < keen:
                when = at(day, random.randint(7, 21), random.randint(0, 59))
                real = history.get(when.strftime("%Y-%m-%dT%H"))
                if when < now and real and when > p["created"]:
                    rows.append(one_reading(p, when, real, ratios))
            day += timedelta(days=1)
    rows.sort(key=lambda r: r["Timestamp"])
    return rows


def one_reading(p, when, real, ratios):
    zone_id = p["zone"] if random.random() < 0.88 else random.choice([z["id"] for z in config.ZONES])
    ratio = ratios.get(zone_id, 1.0) if Z_HAS_STATION.get(zone_id) else 1.0
    if Z_HAS_STATION.get(zone_id):
        ref_aqi, ref_source = round(real["aqi_24h"] * ratio * random.uniform(0.96, 1.04)), "CPCB station"
    else:
        ref_aqi, ref_source = real["aqi_24h"], "Model"

    hour_mix = 0.4 * real["aqi_now"] + 0.6 * real["aqi_24h"]
    true_aqi = max(10, min(480, hour_mix * ratio * ZONE_FACTOR[zone_id] * math.exp(random.gauss(0, NOISE))))
    note = random.choice(NOTES[zone_id]) if random.random() < 0.3 else ""
    if random.random() < 0.025:
        # Now and then a monitor is held right next to a source; the site flags these for checking
        true_aqi = min(480, true_aqi * random.uniform(2.3, 2.8))
        note = random.choice(["Reading taken right next to burning waste", "Monitor held near a diesel generator",
                              "Standing behind a bus exhaust"])
    kind = random.random()
    aqi = round(true_aqi) if kind < 0.70 else None
    pm25 = round(pm25_from_aqi(true_aqi) * random.uniform(0.95, 1.05), 1) if 0.55 < kind < 0.92 else None
    if aqi is None and pm25 is None:
        aqi = round(true_aqi)
    temp = None
    if real["temp"] is not None and random.random() < 0.8:
        temp = round(real["temp"] + random.uniform(-1.2, 1.2), 1)

    community = aqi if aqi is not None else airquality.aqi_from_pm(pm25)
    flag = ""
    if abs(community - ref_aqi) > config.FLAG_DIFF_AQI:
        compared_with = "the CPCB station" if ref_source == "CPCB station" else "the model"
        flag = f"Differs from {compared_with} by {abs(community - ref_aqi)}"
    activity = weighted_choice(ACTIVITY_WEIGHTS)
    if p["occupation"].startswith("Outdoor") and random.random() < 0.5:
        activity = "Outdoor work"
    return {
        "Timestamp": stamp(when), "Participant ID": p["id"], "Zone": zone_id,
        "AQI": "" if aqi is None else aqi, "PM2.5": "" if pm25 is None else pm25,
        "Temp (C)": "" if temp is None else temp, "Feel": feel_for(true_aqi, zone_id), "Activity": activity,
        "Note": note, "API AQI": ref_aqi, "Flag": flag, "Ref source": ref_source,
    }


# ---------------------------------------------------------------------------
# CSOD exercise: "About your day" answers and pollution spike check-ins
# ---------------------------------------------------------------------------
def clip(value, low=1, high=5):
    return int(max(low, min(high, round(value))))


def time_of_day(hour):
    return "Morning" if 5 <= hour < 12 else "Afternoon" if hour < 17 else "Evening" if hour < 21 else "Night"


def person_habits(pid):
    """Things that stay the same for one person (their usual app, why they open it, ...)."""
    r = random.Random(pid)
    return {
        "source": r.choices(config.AQI_SOURCES, weights=[30, 20, 14, 10, 16, 8, 2])[0],
        "trigger": r.choices(config.APP_TRIGGERS, weights=[40, 36, 24])[0],
        "change": r.choices(config.APP_CHANGES, weights=[30, 14, 22, 24, 10])[0],
        "cyclist": r.random() < 0.3,
        "gamer": r.random() < 0.35,
    }


def add_day_answers(row, p):
    """Fill the optional CSOD form columns of one reading (about 3 in 4 people answer them)."""
    hour = int(row["Timestamp"][11:13])
    row["Time of day"] = time_of_day(hour)
    if random.random() > 0.78:
        return row
    h = person_habits(p["id"])
    aqi = float(row["AQI"]) if str(row["AQI"]) != "" else airquality.aqi_from_pm(float(row["PM2.5"]))
    bad = (aqi - 150) / 60          # > 0 when the air is worse than usual
    outdoor_job = p["occupation"].startswith("Outdoor") or row["Activity"] in ("Commuting", "Outdoor work", "Exercise")
    resp = p["responsive"]

    sky = random.choices(config.SKY_OPTIONS, weights=[36, 18, 12, 3, 1, 30 if hour < 10 or aqi > 220 else 8])[0]
    acts = set(random.sample(["Studying / working", "Walking", "Shopping", "Coffee / cafe"], random.randint(1, 2)))
    if h["cyclist"] and random.random() > 0.3 + 0.2 * bad:
        acts.add("Cycling")
    if (h["gamer"] and random.random() < 0.6) or (bad > 1.2 and random.random() < 0.25):
        acts.add("Gaming (indoor)")
    if bad > 0.5 and random.random() < 0.4 + 0.3 * resp:
        acts.add("Staying indoors")
    if random.random() < 0.15:
        acts.add("Sports")
    if resp > 0.6 and random.random() < 0.7:
        actions = random.sample(["Mask", "Cancelled outdoor activity", "Changed mode of transport"], random.randint(1, 3))
    elif resp > 0.3:
        actions = ["Mask"]
    else:
        actions = ["Took no action"]

    row.update({
        "AQI source": "Own monitor" if p.get("monitor_own") else h["source"],
        "Sky": sky,
        "Humidity": random.choices(config.HUMIDITY_OPTIONS, weights=[25, 50, 25 + (20 if sky == "Foggy" else 0)])[0],
        "Activities today": "; ".join(a for a in config.DAY_ACTIVITIES if a in acts),
        "Coffee (1-5)": clip(random.gauss(3.1 - 0.3 * bad, 1.0)),
        "Cycling (1-5)": clip(random.gauss((3.6 if h["cyclist"] else 1.8) - 0.6 * bad * resp, 0.8)),
        "Gaming (1-5)": clip(random.gauss((3.4 if h["gamer"] else 2.0) + 0.4 * bad, 0.9)),
        "Study place": "Indoor" if bad > 0.5 and random.random() < 0.8 else random.choices(config.STUDY_PLACES, weights=[5, 2, 4])[0],
        "Comfort outside (1-5)": clip(random.gauss(3.8 - 0.9 * bad, 0.8)),
        "Went outside": "Yes" if outdoor_job or random.random() < 0.82 - 0.15 * max(0, bad) * resp else "No",
        "App trigger": h["trigger"],
        "Poor AQI actions": "; ".join(a for a in config.POOR_AQI_ACTIONS if a in actions),
        "Routine change (1-5)": clip(random.gauss(1.8 + 2.4 * resp, 0.7)),
        "App change wanted": h["change"] if random.random() < 0.85 else random.choice(config.APP_CHANGES),
    })
    return row


def checkin_rows(people, history, day1, now):
    """Group B spots spikes; Group A sends the 3-question check-in to the participants."""
    by_day = {}
    for key, v in history.items():
        d, hour = key[:10], int(key[11:13])
        if 7 <= hour <= 20 and day1.isoformat() <= d < now.date().isoformat():
            if d not in by_day or v["aqi_now"] > by_day[d][1]:
                by_day[d] = (hour, v["aqi_now"])
    spikes = sorted(((d, h, a) for d, (h, a) in by_day.items() if a >= config.SPIKE_AQI), key=lambda s: -s[2])
    if len(spikes) < 4:  # cleaner fortnight: use the worst days instead
        spikes = sorted(((d, h, a) for d, (h, a) in by_day.items()), key=lambda s: -s[2])[:4]
    spikes = sorted(spikes[:5])

    rows = []
    for d, hour, aqi in spikes:
        study_day = (date.fromisoformat(d) - day1).days + 1
        for p in people:
            if p.get("dropout_after") and study_day > p["dropout_after"]:
                continue
            if random.random() > 0.55 + 0.25 * p["responsive"]:
                continue  # didn't answer this time
            when = at(date.fromisoformat(d), hour, 0) + timedelta(minutes=random.randint(15, 230))
            if when >= now or when <= p["created"]:
                continue
            checked = random.random() < 0.4 + 0.35 * p["responsive"] + (0.15 if study_day >= 8 else 0)
            if checked and random.random() < 0.25 + 0.65 * p["responsive"]:
                options = ["Wore a mask", "Closed windows", "Stayed indoors"]
                if p.get("exercises"):
                    options.append("Cancelled a run / outdoor activity")
                changes = random.sample(options, random.randint(1, min(3, len(options))))
            elif not checked and random.random() < 0.2:
                changes = [random.choice(["Closed windows", "Wore a mask"])]
            else:
                changes = ["No change"]
            anxiety = clip(random.gauss(2.0 + (aqi - 200) / 70 + (0.7 if checked else 0), 0.8))
            rows.append({"Timestamp": stamp(when), "Participant ID": p["id"], "Zone": p["zone"], "City AQI": aqi,
                         "Checked app (4h)": "Yes" if checked else "No",
                         "Plan changes": "; ".join(c for c in config.PLAN_CHANGES if c in changes),
                         "Anxiety (1-5)": anxiety})
    rows.sort(key=lambda r: r["Timestamp"])
    return rows


def extend_existing():
    """Add the CSOD answers and check-ins to the dataset already on disk, keeping every ID."""
    participants = storage.read_participants()
    if not participants:
        raise SystemExit("No participants yet. Run without --extend first.")
    survey = storage.read_table(storage.SURVEY)
    diary = storage.read_table(storage.DIARY)
    drs = {}
    for r in survey:
        drs.setdefault(r["Participant ID"], {})[r["Phase"]] = float(r["DRS"])
    last_day = {}
    for r in diary:
        last_day[r["Participant ID"]] = max(last_day.get(r["Participant ID"], ""), r["Date"])
    day1 = date.fromisoformat(min(r["Date"] for r in diary)) if diary else datetime.now(IST).date() - timedelta(days=14)

    people = []
    for row in participants:
        pid = row["Participant ID"]
        d = drs.get(pid, {})
        before, after = d.get(config.SURVEY_PHASES[0]), d.get(config.SURVEY_PHASES[-1])
        responsive = max(0.0, min(1.0, (after - before) / 2.0)) if before is not None and after is not None \
            else random.uniform(0.2, 0.6)
        stopped = last_day.get(pid)
        dropout = None
        if stopped and pid not in {r["Participant ID"] for r in survey if r["Phase"] == config.SURVEY_PHASES[-1]}:
            dropout = (date.fromisoformat(stopped) - day1).days + 1
        people.append({"id": pid, "zone": int(row["Zone"]), "occupation": row["Occupation"],
                       "created": datetime.strptime(row["Created"], "%Y-%m-%d %H:%M").replace(tzinfo=IST),
                       "responsive": responsive, "exercises": random.random() < 0.45,
                       "dropout_after": dropout})
    by_id = {p["id"]: p for p in people}

    readings = storage.read_submissions()
    filled = 0
    for r in readings:
        p = by_id.get(r["Participant ID"])
        if p and not r["Time of day"]:
            add_day_answers(r, p)
            filled += 1
    storage.replace_all_submissions(readings)

    added = 0
    if not storage.read_table(storage.CHECKINS):
        print("Downloading Bhubaneswar's real hourly air to find the pollution spikes ...")
        history = fetch_real_history((datetime.now(IST).date() - day1).days + 2)
        rows = checkin_rows(people, history, day1, datetime.now(IST))
        storage.replace_table(storage.CHECKINS, rows)
        added = len(rows)
    print(f"Added 'About your day' answers to {filled} readings and {added} spike check-ins.")


# ---------------------------------------------------------------------------
# Hotspots (SOP item 9)
# ---------------------------------------------------------------------------
def hotspot_rows(people, day1, now):
    rows = []
    for zone, kind, landmark, desc, study_day in HOTSPOTS:
        when = at(day1 + timedelta(days=study_day - 1), random.randint(8, 19), random.randint(0, 59))
        if when > now:
            continue
        reporters = [p["id"] for p in people if p["zone"] == zone] or [people[0]["id"]]
        age_days = (now - when).days
        if age_days < 2:
            status, note = "Reported", ""                 # not checked yet
        elif kind == "Industrial activity":
            status, note = "Not confirmed", VERIFY_NOTES[kind][1]
        else:
            status, note = "Verified", random.choice(VERIFY_NOTES[kind])
        rows.append({"Timestamp": stamp(when), "Reporter ID": random.choice(reporters), "Zone": zone, "Type": kind,
                     "Landmark": landmark, "Description": desc, "Verification method": config.HOTSPOT_TYPES[kind],
                     "Status": status, "Verification note": note})
    rows.sort(key=lambda h: h["Timestamp"])
    return rows


# ---------------------------------------------------------------------------
def make_sample_data():
    now = datetime.now(IST)
    today = now.date()
    day1 = today - timedelta(days=STUDY_DAYS)      # the diary covers the 14 full days before today
    alert_day = 8                                   # personalized alerts start in week 2

    print("Downloading Bhubaneswar's real hourly air for the study period from Open-Meteo ...")
    history = fetch_real_history(STUDY_DAYS + 4)
    ratios = station_ratios()

    people = make_people(day1)
    diary, survey = [], []
    for p in people:
        last = day1 + timedelta(days=p.get("dropout_after", STUDY_DAYS) - 1)
        days = [day1 + timedelta(days=i) for i in range((last - day1).days + 1)]
        days = [d for i, d in enumerate(days) if i in (0, len(days) - 1) or random.random() < p["adherence"]]
        diary += diary_rows(p, days, history, alert_day)
        finished = "dropout_after" not in p and random.random() < 0.95
        after_time = at(day1 + timedelta(days=STUDY_DAYS - 1), random.randint(19, 22), random.randint(0, 59))
        morning = at(today, random.randint(7, 10), random.randint(0, 59))
        if random.random() < 0.3 and morning < now:
            after_time = morning      # a few fill it in the next morning
        survey += survey_rows(p, finished, after_time)

    diary.sort(key=lambda r: (r["Date"], r["Participant ID"], r["Start"]))
    survey.sort(key=lambda r: r["Timestamp"])
    by_id = {p["id"]: p for p in people}
    readings = [add_day_answers(r, by_id[r["Participant ID"]]) for r in reading_rows(people, day1, now, history, ratios)]
    return {
        "participants": participant_rows(people),
        "readings": readings,
        "checkins": checkin_rows(people, history, day1, now),
        "diary": diary, "survey": survey,
        "hotspots": hotspot_rows(people, day1, now),
        "day1": day1,
    }


def clear_all():
    storage.replace_all_submissions([])
    storage.replace_all_participants([])
    for table in (storage.DIARY, storage.SURVEY, storage.HOTSPOTS, storage.CHECKINS):
        storage.replace_table(table, [])
    if os.path.exists(MARKER_FILE):
        os.remove(MARKER_FILE)


if __name__ == "__main__":
    if "--extend" in sys.argv:
        extend_existing()
        sys.exit()

    if "--clear" in sys.argv:
        clear_all()
        print("Cleared readings, participants, diaries, surveys and hotspots.")
        sys.exit()

    if (storage.read_submissions() or storage.read_participants()) and "--force" not in sys.argv:
        print("The data files already have rows. Nothing changed.")
        print("Use  --force  to replace them with sample data, or  --clear  to empty them.")
        sys.exit(1)

    try:
        data = make_sample_data()
    except Exception as error:
        print("Could not download the real air history:", type(error).__name__, error)
        print("Nothing changed. Try again in a few minutes.")
        sys.exit(1)

    storage.replace_all_participants(data["participants"])
    storage.replace_all_submissions(data["readings"])
    storage.replace_table(storage.DIARY, data["diary"])
    storage.replace_table(storage.SURVEY, data["survey"])
    storage.replace_table(storage.HOTSPOTS, data["hotspots"])
    storage.replace_table(storage.CHECKINS, data["checkins"])
    with open(MARKER_FILE, "w", encoding="utf-8") as f:
        f.write("The data in this folder is a generated sample dataset (seed_demo_data.py).\n")

    after = sum(1 for s in data["survey"] if s["Phase"] == config.SURVEY_PHASES[-1])
    diary_days = len({(r["Participant ID"], r["Date"]) for r in data["diary"]})
    print(f"Study period {data['day1']} to {data['day1'] + timedelta(days=STUDY_DAYS - 1)}")
    print(f"  {len(data['participants'])} participants, {diary_days} diary days ({len(data['diary'])} blocks)")
    print(f"  {len(data['survey']) - after} before-alert surveys, {after} after-alert surveys")
    print(f"  {len(data['hotspots'])} hotspot reports, {len(data['readings'])} community readings "
          f"({sum(1 for r in data['readings'] if r['Flag'])} flagged)")
    print("The admin panel shows that sample data is loaded until you clear it.")
