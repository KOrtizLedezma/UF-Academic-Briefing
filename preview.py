import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from calendar_logic import parse_assignments, render_email, upcoming  # noqa: E402

COURSES = {
    "580049": "COP5615 — Distributed Operating Systems",
    "573643": "CDA6325C — Cyber-Physical System Security",
    "566428": "CAP5771 — Introduction to Data Science",
}


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Usage: python preview.py downloaded-calendar.ics [YYYY-MM-DD]")
    path = Path(sys.argv[1])
    now = (datetime.fromisoformat(sys.argv[2]).replace(hour=8, tzinfo=ZoneInfo("America/New_York"))
           if len(sys.argv) == 3 else datetime.now(ZoneInfo("America/New_York")))
    parsed = parse_assignments(path.read_bytes(), COURSES)
    due = upcoming(parsed, now, 7)
    _, html_body, text_body = render_email(due, now, 7)
    print(f"Selected-course assignments in downloaded feed: {len(parsed)}")
    print(text_body)
    output = Path.cwd() / "preview.html"
    output.write_text(html_body, encoding="utf-8")
    print(f"HTML preview saved to {output}")


if __name__ == "__main__":
    main()
