from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import escape
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

TIME_ZONE = ZoneInfo("America/New_York")
COURSE_ID_RE = re.compile(r"(?:[?&])include_contexts=course_(\d+)(?:[&#]|$)")
ASSIGNMENT_UID_RE = re.compile(r"^event-assignment-(\d+)$")
TRAILING_COURSE_RE = re.compile(r"\s+\[[^\]]+\]$")
TEXT_ESCAPE_RE = re.compile(r"\\([nN,;\\])")
MAX_FEED_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Assignment:
    uid: str
    course: str
    course_id: str
    title: str
    due: date | datetime
    canvas_url: str

    @property
    def due_date(self) -> date:
        if isinstance(self.due, datetime):
            return self.due.astimezone(TIME_ZONE).date()
        return self.due


def unfold_ical_lines(text: str) -> list[str]:
    lines = []
    for raw in text.lstrip("\ufeff").splitlines():
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _decode_text(value: str) -> str:
    return TEXT_ESCAPE_RE.sub(lambda match: "\n" if match[1].lower() == "n" else match[1], value)


def _parse_dtstart(property_name: str, value: str) -> date | datetime:
    if re.search(r"(?:^|;)VALUE=DATE(?:;|$)", property_name, re.I) or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value, "%Y%m%d").date()
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
    tzid = re.search(r"(?:^|;)TZID=([^;:]+)", property_name, re.I)
    return parsed.replace(tzinfo=ZoneInfo(tzid[1]) if tzid else TIME_ZONE)


def _event_assignment(fields: dict[str, tuple[str, str]], courses: dict[str, str]) -> Assignment | None:
    uid = fields.get("UID", ("", ""))[1]
    id_match = ASSIGNMENT_UID_RE.fullmatch(uid)
    if not id_match:  # excludes lectures and ordinary Canvas calendar events
        return None
    original_url = fields.get("URL", ("", ""))[1]
    match = COURSE_ID_RE.search(original_url)
    if not match or match[1] not in courses:
        return None
    if "DTSTART" not in fields:
        raise ValueError(f"Selected assignment {uid} has no DTSTART")
    prop_name, raw_due = fields["DTSTART"]
    raw_summary = _decode_text(fields.get("SUMMARY", ("", ""))[1])
    title = TRAILING_COURSE_RE.sub("", raw_summary).strip()
    course_id = match[1]
    return Assignment(
        uid=uid,
        course_id=course_id,
        course=courses[course_id],
        title=title or "Untitled assignment",
        due=_parse_dtstart(prop_name, raw_due),
        canvas_url=f"https://ufl.instructure.com/courses/{course_id}/assignments/{id_match[1]}",
    )


def parse_assignments(ics: bytes | str, courses: dict[str, str]) -> list[Assignment]:
    if isinstance(ics, bytes):
        if len(ics) > MAX_FEED_BYTES:
            raise ValueError("Canvas feed is too large")
        text = ics.decode("utf-8-sig")
    else:
        text = ics
    if "BEGIN:VCALENDAR" not in text:
        raise ValueError("Response was not an iCalendar feed")
    by_uid: dict[str, Assignment] = {}
    inside_event = False
    fields: dict[str, tuple[str, str]] = {}
    for line in unfold_ical_lines(text):
        if line == "BEGIN:VEVENT":
            inside_event, fields = True, {}
        elif line == "END:VEVENT" and inside_event:
            item = _event_assignment(fields, courses)
            if item:
                by_uid[item.uid] = item
            inside_event = False
        elif inside_event and ":" in line:
            key, value = line.split(":", 1)
            bare_key = key.split(";", 1)[0].upper()
            if bare_key in {"UID", "URL", "SUMMARY", "DTSTART"}:
                fields[bare_key] = (key, value)
    return sorted(by_uid.values(), key=lambda a: (a.due_date, a.course, a.title))


def upcoming(assignments: list[Assignment], now: datetime, days_ahead: int = 7) -> list[Assignment]:
    now_et = now.astimezone(TIME_ZONE)
    selected = []
    for item in assignments:
        diff = (item.due_date - now_et.date()).days
        if not (0 <= diff <= days_ahead):
            continue
        if isinstance(item.due, datetime) and item.due.astimezone(TIME_ZONE) < now_et:
            continue
        selected.append(item)
    return selected


def _due_label(item: Assignment) -> str:
    if isinstance(item.due, datetime):
        local = item.due.astimezone(TIME_ZONE)
        return f"{local:%a, %b} {local.day} · {local:%I:%M %p %Z}".replace("· 0", "· ")
    return f"{item.due:%a, %b} {item.due.day} · time not provided"


def _group(item: Assignment, today: date) -> str:
    diff = (item.due_date - today).days
    return "Due today" if diff == 0 else "Due tomorrow" if diff == 1 else "Coming up"


def render_email(assignments: list[Assignment], now: datetime, days_ahead: int) -> tuple[str, str, str]:
    today = now.astimezone(TIME_ZONE).date()
    subject = f"UF Academic Briefing — {today:%b} {today.day}, {today.year}"
    rows_html = []
    rows_text = []
    for heading in ("Due today", "Due tomorrow", "Coming up"):
        members = [a for a in assignments if _group(a, today) == heading]
        if not members:
            continue
        rows_html.append(f'<h2 style="color:#17365d;font-size:18px;margin:25px 0 10px">{heading}</h2>')
        rows_text.append(f"\n{heading.upper()}")
        for item in members:
            rows_html.append(
                '<div style="padding:12px 15px;border:1px solid #dfe6ed;'
                'border-radius:8px;margin:8px 0;background:#ffffff">'
                f'<b style="color:#34517c">{escape(item.course)}</b><br>'
                f'<a href="{escape(item.canvas_url, quote=True)}" '
                f'style="color:#0d5ca8">{escape(item.title)}</a><br>'
                f'<small style="color:#525f6a">{escape(_due_label(item))}</small></div>'
            )
            rows_text.append(f"- {item.course}: {item.title} — {_due_label(item)}\n  {item.canvas_url}")
    if not assignments:
        rows_html.append('<p>No listed assignment deadlines in this window.</p>')
        rows_text.append("No listed assignment deadlines in this window.")
    caution = ("The Canvas iCal feed does not show submission status. "
               "For date-only items, verify the exact submission cutoff in Canvas.")
    html_body = (
        '<!doctype html><html><body style="margin:0;background:#f3f6fa;'
        'font-family:Arial,Helvetica,sans-serif;color:#15243a">'
        '<main style="max-width:650px;margin:auto;padding:25px">'
        f'<h1 style="color:#17365d;margin-bottom:0">UF Academic Briefing</h1>'
        f'<p>{today:%A, %B} {today.day}, {today.year} · '
        f'{len(assignments)} deadline(s) today + next {days_ahead} days</p>'
        + "".join(rows_html)
        + f'<p style="color:#677582;font-size:12px;margin-top:30px">{escape(caution)}</p>'
        '</main></body></html>'
    )
    text_body = (f"{subject}\n{len(assignments)} listed deadline(s) today + next {days_ahead} days\n"
                 + "\n".join(rows_text) + f"\n\n{caution}\n")
    return subject, html_body, text_body
