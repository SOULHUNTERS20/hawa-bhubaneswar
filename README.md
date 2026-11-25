# Hawa Bhubaneswar

A citizen-science air quality platform for Bhubaneswar, built for the CSOD Citizen Science
Exercise (Autumn 2026) by **Group A5**.

**Live site:** https://soulhunter.pythonanywhere.com

Official monitors only cover a few fixed points. Hawa Bhubaneswar collects hyperlocal readings
from people in 5 contrasting zones of the city and compares them with the official CPCB stations
and satellite model data. It also runs the group's 14-day study protocol:

- **Anonymous registration** with consent (IDs like `BBSR-Z3-482`, no names or phone numbers)
- **Time-activity diary** that works out each person's Personal Air Quality Exposure (PAQE) from
  hourly PM2.5, indoor infiltration factors and breathing rates, with personalised alerts
- **Decision-making surveys** before and after the alerts (Decision Responsiveness Score)
- **Pollution hotspot register** with student verification
- **Spike check-ins** and **weekly zone insights** shared back with participants
- **Admin panel** to review, edit and export every table

Built with Python (Flask), plain HTML/CSS/JavaScript, Chart.js and Leaflet. Data comes from
Open-Meteo (CAMS) and the CPCB/OSPCB stations via OpenAQ. There's no database: everything is stored
in markdown tables.

**Community data, not official. Not for medical decisions.**

### Credits

Group A5, CSOD Citizen Science Exercise, Autumn 2026:
<!-- Add your group members' names here -->

Licensed under the MIT Licence (see `LICENSE`).

---

## What's in the folder

```
hawa-bhubaneswar/
├── app.py              Flask server: pages, JSON API, validation, admin
├── config.py           EDIT ME: zones, survey options, limits
├── storage.py          Reads/writes the markdown "database" files
├── airquality.py       CPCB AQI maths + Open-Meteo/OpenAQ fetch + 30-minute cache
├── assistant.py        "Ask Hawa" AI assistant (Google Gemini, free tier)
├── study.py            Standard Operating Protocol pages + APIs (registration, diary, survey, hotspots)
├── exposure.py         PAQE maths: hourly PM2.5 x infiltration x breathing rate, alerts
├── admin_panel.py      Admin panel table editor (edit, delete, withdraw, overview numbers)
├── seed_demo_data.py   Makes an SOP sample dataset (and clears it)
├── requirements.txt    Python packages
├── data/
│   ├── submissions.md  Community readings (markdown table)
│   ├── participants.md Participant IDs + profiles
│   ├── diary.md        Time-activity diary blocks with PAQE
│   ├── survey.md       Decision-making survey answers + DRS
│   └── hotspots.md     Hotspot register
├── templates/          HTML pages (Jinja templates, all extend base.html)
└── static/
    ├── css/style.css   All styling, light + dark mode
    └── js/             One small script per page + common.js
```

---

## Run it on Windows

You only do steps 1 to 3 once.

**1. Install Python** (3.10 or newer)
Download it from https://www.python.org/downloads/ and run the installer.
On the first screen, **tick "Add python.exe to PATH"**, then click Install.
Close and reopen any PowerShell windows afterwards.

**2. Open PowerShell in this folder**
Open the `hawa-bhubaneswar` folder in File Explorer, click the address bar, type
`powershell` and press Enter.

**3. Create a virtual environment and install the packages**

```powershell
python -m venv venv
.\venv\Scripts\python -m pip install -r requirements.txt
```

**4. Set an admin password** (do this each time you open a new PowerShell window)

```powershell
$env:ADMIN_PASSWORD = "pick-a-long-password"
```

If you skip this, the site still works but the Admin page stays switched off.

Optional, for official CPCB station data (see "Official station data" below):

```powershell
$env:OPENAQ_API_KEY = "your-openaq-key"
```

**5. Start the site**

```powershell
.\venv\Scripts\python app.py
```

Open **http://127.0.0.1:5000** in your browser. Press `Ctrl + C` in PowerShell to stop.

> Tip: `debug=True` is on, so the server restarts by itself when you save a `.py` file.
> Just refresh the browser after editing HTML/CSS/JS.

---

## Sample data

`seed_demo_data.py` fills every data file with a **generated** sample dataset that
follows the SOP: 30 participants with profiles, a 14-day diary each (with PAQE from
Bhubaneswar's real hourly PM2.5), before/after surveys with DRS, a hotspot register
and community readings based on the real air of those days.

```powershell
.\venv\Scripts\python seed_demo_data.py           # only works if the files are empty
.\venv\Scripts\python seed_demo_data.py --force   # replace everything with a new sample dataset
.\venv\Scripts\python seed_demo_data.py --clear   # empty every file
```

While it is loaded, the admin panel says so and has a **Clear sample data** button.
Clear it before real participants start, so generated rows never mix with real ones.

---

## Pages

| URL | Page |
|---|---|
| `/` | Home: intro, live stats, zone cards, how to take part |
| `/map` | Leaflet map, one CPCB-coloured marker per zone |
| `/live` | Official CPCB station (zones 3, 5) + Open-Meteo model for every zone |
| `/calculator` | Personal AQI (pAQI) calculator with what-if ideas |
| `/submit` | Daily survey form |
| `/participant` | Get / link / forget your participant ID |
| `/data` | Public table, charts, .md and .csv downloads |
| `/ask` | Ask Hawa: AI assistant that answers questions using the site's data |
| `/participate` | Take part: the SOP steps with your progress and today's personalized alert |
| `/diary` | SOP step 7: time-activity diary, hourly PM2.5, PAQE, alerts |
| `/survey` | SOP steps 8 + 10: decision-making questions (Likert), DRS, persistence |
| `/hotspots` | SOP step 9: hotspot register with student verification |
| `/checkin` | CSOD Phase 3: 3-question pollution spike check-in (send the link during spikes) |
| `/advisory` | General AQI advisory (CPCB bands) + posters from `static/posters/` |
| `/ethics` | Ethics and consent |
| `/admin` | Admin panel: study overview, search / edit / delete every table, verify hotspots, withdraw a participant, exports |

---

## Editing things

- **Zones**: edit `ZONES` in `config.py` (name, type, description, lat/lon).
- **Survey answers**: `FEEL_OPTIONS` and `ACTIVITY_OPTIONS` in `config.py`.
- **Limits**: rate limit, flag threshold, cache time, note length are in `config.py`.
- **pAQI factors** (infiltration, breathing rates, masks): top of `static/js/calculator.js`.
- **Colours / fonts**: variables at the top of `static/css/style.css`.

## Data rules (enforced in `app.py`)

- AQI 0–500, PM2.5 0–999, temperature −5 to 55 °C, note max 100 characters.
- `|` and newlines are stripped from every value so the markdown table can't break.
- 1 submission per participant ID every 2 hours.
- Readings more than 100 AQI points away from the official value for that zone
  (CPCB station if there is one, otherwise the model) are **flagged** (kept, not
  deleted) in the `Flag` column.
- Three extra columns come after `Note`: `API AQI` (the official value at the moment
  of submission, used for "community vs official"), `Flag`, and `Ref source`
  (`CPCB station` or `Model`).

## About the "live" numbers

The site uses two sources:

- **Official CPCB stations**, read through **OpenAQ** (a non-profit that republishes
  government air data). Bhubaneswar has two real monitors, run by the Odisha State
  Pollution Control Board: **Patia** (zone 3) and **Lingraj Mandir** (zone 5).
  Zones 1, 2 and 4 have no official monitor.
- **Open-Meteo model** (European CAMS) for every zone. It works on ~40 km grid squares,
  so it usually shows the same value for all five zones.

Both are turned into an AQI using CPCB breakpoints on PM2.5 and PM10 (latest hour for
stations, 24-hour average for the model). That is a fair PM-based value, but the full
official CPCB AQI uses 24-hour averages and also gases (NO₂, SO₂, O₃, CO).

Why not data.gov.in? It is the government's own source, but it blocks servers outside
India, and PythonAnywhere's servers are in the US/Europe.

## Official station data (OpenAQ)

1. Register (free) at https://explore.openaq.org → sign in → account settings → copy your **API key**.
2. Give the key to the site as the environment variable `OPENAQ_API_KEY`:
   - locally: `$env:OPENAQ_API_KEY = "your-key"` before starting the site
   - on PythonAnywhere: add `os.environ["OPENAQ_API_KEY"] = "your-key"` to the WSGI file
3. Check it works (PythonAnywhere Bash console, inside the project folder):
   ```bash
   OPENAQ_API_KEY="your-key" venv/bin/python airquality.py
   ```
   It lists every station OpenAQ has around Bhubaneswar and which zone each one feeds.
4. Without a key, everything still works and every zone uses the model.

If a station has a different name on OpenAQ, edit the `station` words for that zone
in `config.py`.

## Standard Operating Protocol (SOP, Group A)

The study follows the group's SOP. Settings are in the SOP section of `config.py`.

| SOP item | Where | Stored in |
|---|---|---|
| 1 Consent, 2 anonymous ID (target 30), 3 city + zone, 4 age group, 5 gender, 6 occupation/workplace | `/participant` (registration form) | `data/participants.md` |
| 7 Time-activity diary for 14 days, hourly PM2.5, PAQE, personalized alerts | `/diary`, alert on `/participate` | `data/diary.md` |
| 8 Decision-making questions (5-point Likert) → DRS = ΣSₖ / m | `/survey` (before + after alerts) | `data/survey.md` |
| 9 Citizen-reported pollution hotspot register + student verification | `/hotspots`, verified on `/admin` | `data/hotspots.md` |
| 10 Do exposure-management behaviours persist? (Yes/No) | `/survey` (after alerts) | `data/survey.md` |
| General AQI advisory (posters) | `/advisory`, images in `static/posters/` | – |
| A–C Hyper-local data, infiltration factors, breathing rates, sample calculation | `exposure.py`, method box on `/diary` | – |

* **PAQE** = Hours × (Outdoor PM2.5 × infiltration factor) × breathing rate. Factors: open
  windows 0.8, closed/HEPA 0.2, road/park 1.0; breathing: rest/desk 0.5, light walking 1.0,
  commuting 1.2, heavy exercise 2.5. The SOP's sample calculation gives exactly **139**.
* **Hourly PM2.5**: the SOP names the Google Air Quality API, which is paid; the site uses
  Open-Meteo (CAMS) hourly history and forecasts for each zone instead (free).
* **Privacy**: the Data page shows profiles, diaries and surveys only as group totals. Raw files
  (with IDs) are downloadable only from `/admin`.

## Ask Hawa (AI assistant, Google Gemini free tier)

`/ask` is a chat where visitors ask questions ("Is it okay to jog in Patia today?").
Each question is sent to Google's Gemini API together with a short summary of the
site's live data and the last 7 days of community readings. Questions are not
saved on our server.

1. Get a free key at https://aistudio.google.com → **Get API key** → **Create API key**.
2. Give it to the site as `GEMINI_API_KEY` (WSGI file on PythonAnywhere, or
   `$env:GEMINI_API_KEY = "your-key"` locally). Without it, Ask Hawa is switched off.
3. Settings in `config.py`: `GEMINI_MODEL` (default `gemini-3.5-flash-lite`, the free
   model with the highest daily limit), questions per visitor per hour, and a daily cap
   for the whole site so the free quota isn't used up.

**Rules of the free tier (Google's terms):** users must be **18 or older**; Google may
use questions and answers to improve its products and people may review them, so
visitors must never type personal information. The Ask Hawa page and the Ethics page
say this. Check your real limits in Google AI Studio; Google can change them.

---

## Deploying it

**Important:** this app saves data in files (`data/*.md`). Many free hosts
(Vercel, Render free, Railway, Heroku) **wipe files** on every restart or redeploy,
which would delete your submissions. Use a host with a persistent disk.

**Recommended: PythonAnywhere (free tier works)**

1. Make an account at https://www.pythonanywhere.com/.
2. Upload this folder (zip it, upload in the **Files** tab, then unzip from a
   **Bash console** with `unzip hawa-bhubaneswar.zip`), or `git clone` it there.
3. In the Bash console:
   `cd hawa-bhubaneswar && python3 -m venv venv && venv/bin/pip install -r requirements.txt`
4. **Web** tab → *Add a new web app* → *Manual configuration* → choose the same Python version.
5. Set **Virtualenv** to `/home/YOURNAME/hawa-bhubaneswar/venv`.
6. Edit the **WSGI configuration file** so it contains only:
   ```python
   import os, sys
   os.environ["ADMIN_PASSWORD"] = "pick-a-long-password"
   os.environ["SECRET_KEY"] = "any-long-random-text"
   os.environ["OPENAQ_API_KEY"] = "your-openaq-key"   # optional
   os.environ["GEMINI_API_KEY"] = "your-gemini-key"   # optional, for Ask Hawa
   sys.path.insert(0, "/home/YOURNAME/hawa-bhubaneswar")
   from app import app as application
   ```
7. Click **Reload**. Your site is at `https://YOURNAME.pythonanywhere.com`.
8. Free accounts can only call websites on PythonAnywhere's allowlist. Both sources
   this site uses (`air-quality-api.open-meteo.com`, `api.open-meteo.com` and
   `api.openaq.org`) are on it.

**Updating the site later** (keeps your data): zip the project **without** the
`venv` and `data` folders, upload the zip, and in a Bash console run
`unzip -o yourzip.zip -d hawa-bhubaneswar`, then click **Reload** on the Web tab.

**Before going public**

- Use a long admin password and set `SECRET_KEY`.
- Never run with `debug=True` on a public server (PythonAnywhere doesn't use the
  `app.run(...)` line, so you're fine there).
- Download `data/submissions.md` regularly as a backup.
- On any other host, the start command is `gunicorn app:app`.
