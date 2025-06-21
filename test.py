import os
import caldav
from dotenv import load_dotenv

load_dotenv()

CALDAV_URL = os.getenv("CALDAV_URL", "https://caldav.example.com")
CALDAV_USERNAME = os.getenv("CALDAV_USERNAME", "John Doe")
CALDAV_PASSWORD = os.getenv("CALDAV_PASSWORD", "password123")

client = caldav.DAVClient(
    url=CALDAV_URL, username=CALDAV_USERNAME, password=CALDAV_PASSWORD
)


# get events from Primary


calendars = client.principal().calendars()
print("Calendars:" f"{[str(calendar.name) for calendar in calendars]}")

primary_calendar = calendars[4]
events = primary_calendar.events() if primary_calendar else []
for event in events:
    print(
        f"Event: {event.vobject_instance.vevent.summary.value} at {event.vobject_instance.vevent.dtstart.value}"
    )
