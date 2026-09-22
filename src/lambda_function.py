"""Lambda: fetch a private Canvas feed and email a filtered daily briefing."""
import os
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from calendar_logic import MAX_FEED_BYTES, parse_assignments, render_email, upcoming

TIME_ZONE = ZoneInfo("America/New_York")


def fetch_feed(feed_url: str) -> bytes:
    # The link is a secret: never log it or insert it into messages.
    parsed = urlparse(feed_url.strip())
    if parsed.scheme != "https" or parsed.hostname != "ufl.instructure.com":
        raise ValueError("Expected an HTTPS UF Canvas calendar feed URL")
    req = Request(feed_url, headers={"User-Agent": "UF-Academic-Briefing/1.0"})
    try:
        with urlopen(req, timeout=15) as response:
            payload = response.read(MAX_FEED_BYTES + 1)
    except (HTTPError, URLError, TimeoutError):
        raise RuntimeError("Could not retrieve Canvas calendar feed; verify URL in SSM") from None
    if len(payload) > MAX_FEED_BYTES:
        raise ValueError("Canvas calendar feed exceeded the 5 MB limit")
    return payload


def lambda_handler(event, context):
    # Import here: the included Lambda Python runtime provides boto3.
    import boto3

    ssm = boto3.client("ssm")
    param_name = os.environ["CANVAS_FEED_PARAMETER"]
    feed_url = ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]
    course_ids = [s.strip() for s in os.environ["COURSE_IDS"].split(",") if s.strip()]
    courses = {
        "580049": "COP5615 — Distributed Operating Systems",
        "573643": "CDA6325C — Cyber-Physical System Security",
        "566428": "CAP5771 — Introduction to Data Science",
    }
    # For a future semester's ID, display the ID until its friendly name is added.
    selected_courses = {cid: courses.get(cid, f"Canvas course {cid}") for cid in course_ids}
    days_ahead = int(os.environ.get("DAYS_AHEAD", "7"))
    if not 0 <= days_ahead <= 365:
        raise ValueError("DAYS_AHEAD must be 0–365")
    now = datetime.now(TIME_ZONE)
    all_selected = parse_assignments(fetch_feed(feed_url), selected_courses)
    due = upcoming(all_selected, now, days_ahead)
    subject, html_body, text_body = render_email(due, now, days_ahead)

    ses = boto3.client("ses")
    email = os.environ["EMAIL_ADDRESS"]
    ses.send_email(
        Source=email,
        Destination={"ToAddresses": [email]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": text_body, "Charset": "UTF-8"},
                "Html": {"Data": html_body, "Charset": "UTF-8"},
            },
        },
    )
    # Log counts only, not the subscription URL or assignment descriptions.
    print(f"Sent briefing: {len(due)} upcoming assignments across {len(selected_courses)} selected courses")
    return {"statusCode": 200, "sent": True, "assignment_count": len(due)}