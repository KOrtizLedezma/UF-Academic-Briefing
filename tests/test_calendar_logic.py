import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from calendar_logic import parse_assignments, upcoming, render_email

COURSES = {"580049": "COP5615", "573643": "CDA6325C"}
FEED = r"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-calendar-event-123
DTSTART:20260923T143000Z
SUMMARY:Lecture [COP5615]
URL;VALUE=URI:https://ufl.instructure.com/calendar?include_contexts=course_580049&month=09&year=2026#calendar_event_123
END:VEVENT
BEGIN:VEVENT
UID:event-assignment-7314303
DTSTART;VALUE=DATE;VALUE=DATE:20260925
SUMMARY:Project 1 [COP5615]
URL;VALUE=URI:https://ufl.instructure.com/calendar?include_contexts=course_
 580049&month=09&year=2026#assignment_7314303
END:VEVENT
BEGIN:VEVENT
UID:event-assignment-200
DTSTART:20260923T170000Z
SUMMARY:Quiz 3 [CDA4324C]
URL;VALUE=URI:https://ufl.instructure.com/calendar?include_contexts=course_573643&month=09&year=2026#assignment_200
END:VEVENT
BEGIN:VEVENT
UID:event-assignment-300
DTSTART;VALUE=DATE:20260925
SUMMARY:Exclude me [CAP5771]
URL;VALUE=URI:https://ufl.instructure.com/calendar?include_contexts=course_566428&month=09&year=2026#assignment_300
END:VEVENT
END:VCALENDAR
"""


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.items = parse_assignments(FEED, COURSES)
        self.now = datetime(2026, 9, 22, 8, tzinfo=ZoneInfo("America/New_York"))

    def test_filters_lectures_and_other_courses(self):
        self.assertEqual(len(self.items), 2)
        self.assertEqual({item.title for item in self.items}, {"Project 1", "Quiz 3"})

    def test_parses_course_and_direct_assignment_url(self):
        project = next(a for a in self.items if a.title == "Project 1")
        self.assertEqual(project.course_id, "580049")
        self.assertEqual(project.canvas_url,
                         "https://ufl.instructure.com/courses/580049/assignments/7314303")
        self.assertNotIsInstance(project.due, datetime)

    def test_timezone_and_inclusion(self):
        self.assertEqual(len(upcoming(self.items, self.now, 7)), 2)
        self.assertEqual(len(upcoming(self.items, self.now, 1)), 1)
        self.assertEqual(len(upcoming(self.items, datetime(2026, 9, 23, 15,
                         tzinfo=ZoneInfo("America/New_York")), 7)), 1)

    def test_date_only_and_email(self):
        _, html, plain = render_email(self.items, self.now, 7)
        self.assertIn("time not provided", plain)
        self.assertIn("Project 1", html)
        self.assertIn("CDA6325C", plain)
        self.assertNotIn("Lecture", html)

    def test_html_escaping(self):
        altered = FEED.replace("Project 1 [COP5615]", "Project <script>bad</script> [COP5615]")
        _, html, _ = render_email(parse_assignments(altered, COURSES), self.now, 7)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()