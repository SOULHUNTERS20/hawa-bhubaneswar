"""
storage.py
----------
Reads and writes the "database" files, which are plain markdown tables:

    data/submissions.md   -> one row per community reading
    data/participants.md  -> one row per participant (anonymous ID + profile)
    data/diary.md         -> time-activity diary blocks (SOP item 7)
    data/survey.md        -> decision-making survey answers + DRS (SOP items 8, 10)
    data/hotspots.md      -> pollution hotspot register (SOP item 9)

Markdown tables look like this:

    | Timestamp | Participant ID | Zone |
    |---|---|---|
    | 2026-11-06 18:30 | BBSR-Z3-482 | 3 |

A "|" or a newline inside a value would break the table, so every value
goes through clean_text() before it is written.
"""

import os
import threading
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SUBMISSIONS_FILE = os.path.join(DATA_DIR, "submissions.md")
PARTICIPANTS_FILE = os.path.join(DATA_DIR, "participants.md")

# The columns asked for in the brief, plus three extra ones at the end:
#   "API AQI"    -> the official / live AQI for that zone at the moment of submission
#                   (this is what powers the "community vs official" comparison)
#   "Flag"       -> filled in when the reading differs wildly from that value
#   "Ref source" -> where "API AQI" came from: "CPCB station" or "Model" (Open-Meteo)
# New columns are only ever added at the END, so older files keep working.
# After those, the CSOD exercise's Google Form questions (all optional).
SUBMISSION_COLUMNS = [
    "Timestamp", "Participant ID", "Zone", "AQI", "PM2.5", "Temp (C)",
    "Feel", "Activity", "Note", "API AQI", "Flag", "Ref source",
    "Time of day", "AQI source", "Sky", "Humidity", "Activities today",
    "Coffee (1-5)", "Cycling (1-5)", "Gaming (1-5)", "Study place", "Comfort outside (1-5)",
    "Went outside", "App trigger", "Poor AQI actions", "Routine change (1-5)", "App change wanted",
]
# SOP items 1-6: consent, anonymous ID, city + residential zone, age group, gender,
# occupation / workplace. Age is stored as a band, never a birth date.
PARTICIPANT_COLUMNS = ["Participant ID", "Zone", "Created", "City", "Age group", "Gender",
                       "Occupation", "Workplace", "Consent"]

SUBMISSIONS_TITLE = (
    "# Hawa Bhubaneswar - Community submissions\n\n"
    "Community data, not official. Not for medical decisions.\n"
)
PARTICIPANTS_TITLE = (
    "# Hawa Bhubaneswar - Participant IDs\n\n"
    "Anonymous IDs only. No names, emails or phone numbers are stored.\n"
)

# Only one request at a time may write to a file (Flask can serve requests in parallel).
_lock = threading.Lock()


def clean_text(value):
    """Make any value safe to put inside a markdown table cell."""
    text = "" if value is None else str(value)
    text = text.replace("|", "/").replace("\r", " ").replace("\n", " ")
    return " ".join(text.split())  # also squashes repeated spaces


# ---------------------------------------------------------------------------
# Generic markdown-table helpers
# ---------------------------------------------------------------------------
def _ensure_file(path, columns, title):
    """
    Create the file with a title and table header if it doesn't exist yet.
    If the file has an older header (fewer columns), rewrite it with the new
    header so the markdown table stays tidy. Existing rows are kept.
    """
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _write_all(path, columns, title, [])
        return
    with open(path, encoding="utf-8") as f:
        header = next((line.strip() for line in f if line.strip().startswith("|")), None)
    if header is not None and header != "| " + " | ".join(columns) + " |":
        _write_all(path, columns, title, _parse(path, columns))


def _row_to_line(columns, row):
    cells = [clean_text(row.get(col, "")) for col in columns]
    return "| " + " | ".join(cells) + " |\n"


def _write_all(path, columns, title, rows):
    """Rewrite the whole file (used when creating it or deleting a row)."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(title + "\n")
        f.write("| " + " | ".join(columns) + " |\n")
        f.write("|" + "---|" * len(columns) + "\n")
        for row in rows:
            f.write(_row_to_line(columns, row))


def _read_all(path, columns, title):
    """Return every row in the table as a list of dictionaries."""
    _ensure_file(path, columns, title)
    return _parse(path, columns)


def _parse(path, columns):
    """Read the markdown table lines of a file into dictionaries."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not (line.startswith("|") and line.endswith("|")):
                continue  # not a table line (title, blank line, text)
            cells = [c.strip() for c in line[1:-1].split("|")]
            if cells[0] == columns[0]:
                continue  # the header row
            if all(set(c) <= set("-: ") for c in cells):
                continue  # the |---|---| separator row
            # Older files may have fewer columns: pad them so nothing crashes.
            cells += [""] * (len(columns) - len(cells))
            rows.append(dict(zip(columns, cells[: len(columns)])))
    return rows


def _append(path, columns, title, row):
    with _lock:
        _ensure_file(path, columns, title)
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(_row_to_line(columns, row))


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------
def read_submissions():
    return _read_all(SUBMISSIONS_FILE, SUBMISSION_COLUMNS, SUBMISSIONS_TITLE)


def add_submission(row):
    _append(SUBMISSIONS_FILE, SUBMISSION_COLUMNS, SUBMISSIONS_TITLE, row)


def replace_all_submissions(rows):
    """Overwrite the whole submissions table (used by seed_demo_data.py)."""
    with _lock:
        _write_all(SUBMISSIONS_FILE, SUBMISSION_COLUMNS, SUBMISSIONS_TITLE, rows)


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------
def read_participants():
    return _read_all(PARTICIPANTS_FILE, PARTICIPANT_COLUMNS, PARTICIPANTS_TITLE)


def find_participant(participant_id):
    for row in read_participants():
        if row["Participant ID"] == participant_id:
            return row
    return None


def replace_all_participants(rows):
    """Overwrite the whole participants table (used by seed_demo_data.py)."""
    with _lock:
        _write_all(PARTICIPANTS_FILE, PARTICIPANT_COLUMNS, PARTICIPANTS_TITLE, rows)


def add_participant_if_new(row):
    """Save a new participant. Returns False if that ID already exists."""
    with _lock:
        if find_participant(row["Participant ID"]):
            return False
        with open(PARTICIPANTS_FILE, "a", encoding="utf-8", newline="\n") as f:
            f.write(_row_to_line(PARTICIPANT_COLUMNS, row))
        return True


def update_participant(participant_id, fields):
    """Change some columns of one participant (e.g. completing the profile). Returns True if found."""
    with _lock:
        rows = read_participants()
        for row in rows:
            if row["Participant ID"] == participant_id:
                row.update({k: v for k, v in fields.items() if k in PARTICIPANT_COLUMNS})
                _write_all(PARTICIPANTS_FILE, PARTICIPANT_COLUMNS, PARTICIPANTS_TITLE, rows)
                return True
        return False


# ---------------------------------------------------------------------------
# Study tables from the Standard Operating Protocol (SOP)
# ---------------------------------------------------------------------------
# SOP item 7: 14-day time-activity diary, one row per time block.
# "PAQE (ug)" = Hours x indoor/micro PM2.5 x breathing rate (the SOP's exposure formula).
DIARY = {
    "path": os.path.join(DATA_DIR, "diary.md"),
    "columns": ["Date", "Participant ID", "Day", "Start", "End", "Location", "Activity", "Hours",
                "Outdoor PM2.5", "Infiltration", "Breathing rate", "Micro PM2.5", "PAQE (ug)", "Source"],
    "title": "# Hawa Bhubaneswar - Time-activity diary (SOP item 7)\n\n"
             "PAQE = Hours x (Outdoor PM2.5 x Infiltration factor) x Breathing rate.\n",
}
# SOP items 8 and 10: decision-making questions on a 5-point Likert scale, the
# Decision Responsiveness Score (DRS = sum of scores / number of questions),
# and whether the behaviours persist after the alert intervention (Yes/No).
SURVEY = {
    "path": os.path.join(DATA_DIR, "survey.md"),
    "columns": ["Timestamp", "Participant ID", "Phase", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6",
                "DRS", "Practices", "Persist"],
    "title": "# Hawa Bhubaneswar - Decision-making survey (SOP items 8 and 10)\n\n"
             "Likert: 1 Never, 2 Rarely, 3 Sometimes, 4 Frequently, 5 Always. DRS = sum of Q1-Q6 / 6.\n",
}
# SOP item 9: citizen-reported pollution hotspot register with student verification.
HOTSPOTS = {
    "path": os.path.join(DATA_DIR, "hotspots.md"),
    "columns": ["Timestamp", "Reporter ID", "Zone", "Type", "Landmark", "Description",
                "Verification method", "Status", "Verification note"],
    "title": "# Hawa Bhubaneswar - Citizen-reported pollution hotspot register (SOP item 9)\n\n"
             "Reports are verified by students before being treated as confirmed. No causation is attributed.\n",
}
# CSOD Phase 3 micro-survey, sent during pollution spikes.
CHECKINS = {
    "path": os.path.join(DATA_DIR, "checkins.md"),
    "columns": ["Timestamp", "Participant ID", "Zone", "City AQI", "Checked app (4h)", "Plan changes",
                "Anxiety (1-5)"],
    "title": "# Hawa Bhubaneswar - Pollution spike check-ins (CSOD Phase 3 micro-survey)\n\n"
             "Did you look at your AQI app in the last 4 hours? Did it change your plans? Pollution anxiety 1-5.\n",
}


def read_table(table):
    return _read_all(table["path"], table["columns"], table["title"])


def append_row(table, row):
    _append(table["path"], table["columns"], table["title"], row)


def replace_table(table, rows):
    with _lock:
        _write_all(table["path"], table["columns"], table["title"], rows)


def replace_diary_day(participant_id, date, new_rows):
    """Save one participant's diary for one date (replacing an earlier save of that date)."""
    with _lock:
        rows = [r for r in read_table(DIARY)
                if not (r["Participant ID"] == participant_id and r["Date"] == date)]
        rows.extend(new_rows)
        # "Day" counts from the person's first diary date, so renumber in case an earlier date was added
        mine = [r["Date"] for r in rows if r["Participant ID"] == participant_id]
        if mine:
            first = date.fromisoformat(min(mine))
            for r in rows:
                if r["Participant ID"] == participant_id:
                    r["Day"] = (date.fromisoformat(r["Date"]) - first).days + 1
        rows.sort(key=lambda r: (r["Date"], r["Participant ID"], r["Start"]))
        _write_all(DIARY["path"], DIARY["columns"], DIARY["title"], rows)


def replace_survey_answer(row):
    """Save a survey answer, replacing the same person's earlier answer for that phase. Returns all rows."""
    with _lock:
        rows = [r for r in read_table(SURVEY)
                if not (r["Participant ID"] == row["Participant ID"] and r["Phase"] == row["Phase"])]
        rows.append({k: clean_text(v) for k, v in row.items()})
        _write_all(SURVEY["path"], SURVEY["columns"], SURVEY["title"], rows)
        return rows


# The two original tables in the same shape as the study tables (used by the admin editor)
SUBMISSIONS = {"path": SUBMISSIONS_FILE, "columns": SUBMISSION_COLUMNS, "title": SUBMISSIONS_TITLE}
PARTICIPANTS = {"path": PARTICIPANTS_FILE, "columns": PARTICIPANT_COLUMNS, "title": PARTICIPANTS_TITLE}


def update_row(table, index, original, fields):
    """
    Admin: change some columns of row number `index`.
    `original` is the row as the admin saw it; if the file changed since then
    (someone else edited or deleted a row) nothing is saved and False is returned.
    """
    with _lock:
        rows = read_table(table)
        if not (0 <= index < len(rows)) or rows[index] != original:
            return False
        rows[index].update({k: clean_text(v) for k, v in fields.items() if k in table["columns"]})
        _write_all(table["path"], table["columns"], table["title"], rows)
        return True


def delete_row(table, index, original):
    """Admin: delete row number `index` if it still matches `original`."""
    with _lock:
        rows = read_table(table)
        if not (0 <= index < len(rows)) or rows[index] != original:
            return False
        rows.pop(index)
        _write_all(table["path"], table["columns"], table["title"], rows)
        return True


def delete_where(table, column, value):
    """Admin: delete every row whose `column` equals `value`. Returns how many were removed."""
    with _lock:
        rows = read_table(table)
        keep = [r for r in rows if r[column] != value]
        if len(keep) != len(rows):
            _write_all(table["path"], table["columns"], table["title"], keep)
        return len(rows) - len(keep)


def blank_where(table, column, value):
    """Admin: empty `column` in every row where it equals `value` (e.g. anonymise a reporter)."""
    with _lock:
        rows = read_table(table)
        hits = [r for r in rows if r[column] == value]
        for r in hits:
            r[column] = ""
        if hits:
            _write_all(table["path"], table["columns"], table["title"], rows)
        return len(hits)

