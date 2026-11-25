"""
config.py
---------
All the settings you are most likely to want to change live in this one file.
Edit the zone names, descriptions and coordinates here and the whole site updates.
"""

SITE_NAME = "Hawa Bhubaneswar"

# ---------------------------------------------------------------------------
# The 5 study zones.
#   id          -> zone number (used inside participant IDs, e.g. BBSR-Z3-482)
#   name        -> shown everywhere on the site
#   type        -> short tag shown on cards
#   description -> one line about the zone (edit freely)
#   lat / lon   -> map position, also used to fetch live data from Open-Meteo
#   station     -> words that identify the official CPCB/OSPCB monitoring station
#                  inside this zone (matched against the station name on
#                  OpenAQ, ignoring capitals). None = no official station.
# ---------------------------------------------------------------------------
ZONES = [
    {
        "id": 1,
        "name": "Rasulgarh / Mancheswar",
        "type": "Industrial",
        "description": "Industrial estate with factories, warehouses and heavy truck traffic.",
        "lat": 20.3090,
        "lon": 85.8610,
        "station": None,
    },
    {
        "id": 2,
        "name": "Master Canteen / Unit 1",
        "type": "Traffic hub",
        "description": "Busy junction near the railway station and bus stops, constant traffic.",
        "lat": 20.2680,
        "lon": 85.8410,
        "station": None,
    },
    {
        "id": 3,
        "name": "Patia / Infocity",
        "type": "IT and construction",
        "description": "Fast-growing IT corridor with new buildings and road works.",
        "lat": 20.3480,
        "lon": 85.8150,
        "station": ["patia"],  # "Patia, Bhubaneswar - OSPCB" (near LV Prasad Eye Hospital)
    },
    {
        "id": 4,
        "name": "Nandankanan / Chandaka",
        "type": "Green belt",
        "description": "Forest and zoo area on the city's northern edge, the cleanest air we expect.",
        "lat": 20.3950,
        "lon": 85.8150,
        "station": None,
    },
    {
        "id": 5,
        "name": "Old Town / Lingaraj",
        "type": "Dense old city",
        "description": "Narrow lanes, temples, markets and closely packed homes.",
        "lat": 20.2382,
        "lon": 85.8338,
        "station": ["lingraj", "lingaraj"],  # "Lingraj Mandir, Bhubaneswar - OSPCB"
    },
]

# Official station data comes from OpenAQ (https://openaq.org), a non-profit
# that copies government monitoring data, including CPCB's, from around the world.
# It needs a free API key from https://explore.openaq.org, set as the environment
# variable OPENAQ_API_KEY. Without a key, the site simply uses Open-Meteo.
#
# The box (min longitude, min latitude, max longitude, max latitude) in which
# stations are looked up. This one covers Bhubaneswar.
STATION_BBOX = "85.70,20.15,85.95,20.45"
# Station readings older than this are ignored (the station is probably offline).
STATION_MAX_AGE_HOURS = 24

# Answers allowed in the survey form (the server rejects anything else).
FEEL_OPTIONS = ["Fresh", "Normal", "Dusty", "Smoky", "Chemical smell", "Hard to breathe"]
ACTIVITY_OPTIONS = ["At home", "Commuting", "Office / indoors", "Outdoor work", "Exercise", "Other"]

# How long live data from Open-Meteo is reused before we ask again (seconds).
CACHE_SECONDS = 30 * 60

# One submission per participant ID every this many hours.
RATE_LIMIT_HOURS = 2

# A reading is flagged (not deleted) if it differs from the live API AQI
# for that zone by more than this many AQI points.
FLAG_DIFF_AQI = 100

# Maximum length of the optional note.
NOTE_MAX_CHARS = 100

# ---------------------------------------------------------------------------
# Standard Operating Protocol (SOP), Group A. Edit these to match your SOP.
# ---------------------------------------------------------------------------
GROUP_NAME = "Group A5"
CITY = "Bhubaneswar"
REGISTRATION_TARGET = 30        # SOP item 2: each group registers 30 participants
STUDY_DAYS = 14                 # SOP item 7: time-activity diary for 14 days
PM25_ALERT_LEVEL = 60           # ug/m3. CPCB 24-hour PM2.5 standard; alerts above this

# SOP items 4-6 (registration profile). Ages are bands, never exact ages.
AGE_GROUPS = ["18–24", "25–34", "35–44", "45–59", "60+"]
GENDERS = ["Female", "Male", "Non-binary / other", "Prefer not to say"]
OCCUPATIONS = ["Student", "Office / IT", "Outdoor work (construction, vendor, driver)", "Shop / market",
               "Healthcare", "Home-maker", "Retired", "Other"]
WORKPLACES = ["Indoor, AC with air filter", "Indoor, AC", "Indoor, windows open", "Outdoors",
              "Works / studies from home"]

# SOP section B: infiltration factors (indoor PM2.5 / outdoor PM2.5) per microenvironment.
#   No filtration / open windows: 0.7-0.9   |   Closed windows / HEPA purifier: 0.1-0.3
MICROENVIRONMENTS = {
    "home_open":    {"label": "Home: windows open, no filter", "factor": 0.8},
    "home_closed":  {"label": "Home: windows closed / HEPA purifier", "factor": 0.2},
    "work_filter":  {"label": "Workplace: AC + air filter", "factor": 0.2},
    "work_open":    {"label": "Workplace: windows open", "factor": 0.8},
    "road_open":    {"label": "Road: open air / traffic (walk, bike, auto)", "factor": 1.0},
    "road_closed":  {"label": "Road: closed car / AC bus", "factor": 0.4},
    "outdoor_park": {"label": "Outdoor: park / open space", "factor": 1.0},
}
# SOP section C: breathing (inhalation) rates in m3/hour.
#   Resting / desk work 0.5  |  light walking / commuting ~1.0 (the SOP sample uses 1.2 for a
#   commute)  |  heavy exercise / cycling 2.5-3.0
ACTIVITIES = {
    "sleeping":  {"label": "Sleeping", "rate": 0.5},
    "indoor":    {"label": "Indoor activity / desk work", "rate": 0.5},
    "walking":   {"label": "Light walking", "rate": 1.0},
    "commuting": {"label": "Commuting", "rate": 1.2},
    "exercise":  {"label": "Heavy exercise / cycling / workout", "rate": 2.5},
}
# The SOP's daily data collection sheet (Group A), used as the default diary day.
SOP_STANDARD_DAY = [
    {"start": 6, "end": 8, "location": "home_open", "activity": "indoor"},
    {"start": 8, "end": 9, "location": "road_open", "activity": "commuting"},
    {"start": 9, "end": 17, "location": "work_filter", "activity": "indoor"},
    {"start": 17, "end": 18, "location": "road_open", "activity": "commuting"},
    {"start": 18, "end": 20, "location": "outdoor_park", "activity": "walking"},
    {"start": 20, "end": 30, "location": "home_open", "activity": "sleeping"},  # 30 = 6 AM next day
]

# SOP item 8: decision-making questions (5-point Likert) and SOP item 10.
LIKERT = ["Never", "Rarely", "Sometimes", "Frequently", "Always"]
DECISION_QUESTIONS = [
    "Do you check the air quality before leaving home?",
    "When the AQI is poor, do you change your outdoor activity schedule?",
    "Have you changed your commuting route after receiving an air-quality alert?",
    "Do you avoid exercising outdoors during high-pollution periods?",
    "Do you consider air quality when deciding whether children or elderly family members "
    "should undertake outdoor activities?",
    "How often do you use protective practices (mask, choosing when to ventilate your home, "
    "choice of transport)?",
]
PROTECTIVE_PRACTICES = ["Mask", "Choosing when to ventilate the home", "Choice of transport", "Air purifier"]
SURVEY_PHASES = ["Before alerts", "After alerts"]
PERSIST_QUESTION = "Are you still following the exposure-management changes you made after the alerts?"

# SOP item 9: hotspot types and how students verify each one.
HOTSPOT_TYPES = {
    "Construction dust": "Photograph or field observation, where safe and permitted",
    "Heavy truck movement": "Time and traffic observation",
    "Roadside waste burning": "Citizen report and appropriate authority notification",
    "Road dust resuspension": "Repeat observation and available PM2.5 data",
    "Industrial activity": "Record location and public information, without attributing causation prematurely",
    "Other": "Field observation, where safe",
}
HOTSPOT_STATUSES = ["Reported", "Verified", "Not confirmed"]
HOTSPOTS_PER_ID_PER_DAY = 5

# ---------------------------------------------------------------------------
# CSOD Citizen Science Exercise (Autumn 2026): the Google Form questions, asked
# in the "About your day" part of the Submit page. All optional. The form's
# "Name" question is left out on purpose: the exercise's own ethics rules say
# names must be replaced by a participant ID.
# ---------------------------------------------------------------------------
AQI_SOURCES = ["Google Maps / Google AQI", "AQI.in", "IQAir / AirVisual", "SAMEER (CPCB)", "Weather app",
               "Own monitor", "Other"]
SKY_OPTIONS = ["Sunny", "Cloudy", "Overcast", "Rainy", "Stormy", "Foggy"]
HUMIDITY_OPTIONS = ["Low", "Moderate", "High"]
DAY_ACTIVITIES = ["Coffee / cafe", "Cycling", "Gaming (indoor)", "Studying / working", "Walking", "Sports",
                  "Shopping", "Staying indoors", "Other"]
STUDY_PLACES = ["Indoor", "Outdoor", "Either"]
APP_TRIGGERS = ["Morning routine", "Planning outdoor activities", "Push notifications"]
POOR_AQI_ACTIONS = ["Mask", "Cancelled outdoor activity", "Changed mode of transport", "Took no action"]
APP_CHANGES = ["Colour shift based on my live location", "Digital fog to show how serious it is",
               "Combined exposure risk for my family", "School / office commute triggers to wear a mask",
               "No change needed"]
# 1-5 scales: (column name, question)
FORM_SCALES = [
    ("Coffee (1-5)", "How likely are you to go out for coffee today?"),
    ("Cycling (1-5)", "How likely are you to go cycling today?"),
    ("Gaming (1-5)", "How likely are you to game indoors today?"),
    ("Comfort outside (1-5)", "How comfortable do you feel going outside today?"),
    ("Routine change (1-5)", "How much does the AQI app change your daily routine?"),
]

# Phase 3 micro-survey: a 3-question check-in sent during pollution spikes.
PLAN_CHANGES = ["Cancelled a run / outdoor activity", "Wore a mask", "Stayed indoors", "Closed windows", "No change"]
SPIKE_AQI = 201              # city AQI at or above this (CPCB "Poor") shows the check-in prompt
CHECKIN_EVERY_HOURS = 4      # one check-in per participant per this many hours

# ---------------------------------------------------------------------------
# "Ask Hawa" AI assistant (Google Gemini API, free tier). See assistant.py.
# Needs the environment variable GEMINI_API_KEY (free key from
# https://aistudio.google.com). Without it, Ask Hawa is switched off.
# ---------------------------------------------------------------------------
GEMINI_MODEL = "gemini-3.5-flash-lite"   # free-tier model with the highest daily limit
GEMINI_THINKING_LEVEL = "MINIMAL"        # less "thinking" = faster answers; None to leave it out
ASK_MAX_QUESTION_CHARS = 300             # longest question a visitor can type
ASK_PER_VISITOR_PER_HOUR = 10            # questions one browser can ask per hour
ASK_DAILY_LIMIT = 250                    # questions for the whole site per day (protects the free quota)
