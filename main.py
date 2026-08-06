import caldav
from datetime import date, datetime, timedelta, timezone
from dotenv import load_dotenv
import os
import uuid
from typing import Optional, Dict, Any, List
import zoneinfo

import icalendar
from icalendar import Calendar, Event, Todo

from mcp.server.fastmcp import FastMCP
from pydantic import Field


load_dotenv()

CALDAV_URL = os.getenv("CALDAV_URL", "https://caldav.example.com")
CALDAV_USERNAME = os.getenv("CALDAV_USERNAME", "John Doe")
CALDAV_PASSWORD = os.getenv("CALDAV_PASSWORD", "password123")

client = caldav.DAVClient(
    url=CALDAV_URL, username=CALDAV_USERNAME, password=CALDAV_PASSWORD
)

UTC = timezone.utc

# The server runs wherever it runs (often remote). The timezone must come from
# the client, so every datetime tool accepts a `timezone` parameter (IANA name,
# e.g. "America/Denver"). If omitted, the CALDAV_TIMEZONE env var is used;
# otherwise UTC is assumed.
try:
    DEFAULT_TZ = zoneinfo.ZoneInfo(os.getenv("CALDAV_TIMEZONE", "UTC"))
except Exception:
    DEFAULT_TZ = UTC


def resolve_tz(name: Optional[str]):
    """Resolve a client-supplied IANA timezone name, falling back to the default."""
    if name:
        try:
            return zoneinfo.ZoneInfo(name)
        except Exception:
            pass
    return DEFAULT_TZ


mcp = FastMCP(
    "CalDAV Server",
    instructions=(
        "This is a CalDAV server. Use the tools provided to interact with your "
        "calendars and todos. Datetime tools accept a `timezone` parameter so times "
        "are interpreted and returned in the user's local timezone (converted to/from "
        "UTC for storage)."
    ),
)


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------

def parse_dt_local(value: str, tz) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM' as wall-clock time in `tz` and return it as UTC."""
    naive = datetime.strptime(value, "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=tz).astimezone(UTC)


def parse_date(value: str) -> date:
    """Parse 'YYYY-MM-DD' as a plain date."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def to_utc(dt, tz) -> Optional[datetime]:
    """Normalize a date/datetime to a UTC-aware datetime. Naive values are assumed to be in `tz`."""
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz).astimezone(UTC)
    return dt.astimezone(UTC)


def to_local(dt, tz) -> Optional[datetime]:
    """Convert a date/datetime to `tz` for display. Naive = wall clock in `tz`."""
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def format_dt(dt, tz) -> str:
    """Format a date/datetime for display. Timed values are shown in `tz`."""
    if dt is None:
        return "No time"
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.isoformat()
    return to_local(dt, tz).strftime("%Y-%m-%d %H:%M %Z")


def day_start(d: date, tz) -> datetime:
    """Start of the day in `tz` as a UTC-aware datetime (for filtering stored UTC times)."""
    return datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(UTC)


def day_after(d: date, tz) -> datetime:
    """The day after `d` at 00:00 in `tz` (exclusive upper bound for date filters)."""
    return day_start(d, tz) + timedelta(days=1)


def parse_due(value: str, tz):
    """Parse a due value: 'YYYY-MM-DD' -> date, 'YYYY-MM-DD HH:MM' -> UTC datetime."""
    if ":" in value or len(value.split()) > 1:
        return parse_dt_local(value, tz)
    return parse_date(value)


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------

def _find_calendar(name: str):
    principal = client.principal()
    calendars = principal.calendars()
    calendar = next((cal for cal in calendars if cal.name == name), None)
    if not calendar:
        raise LookupError(f"Calendar '{name}' not found.")
    return calendar


def _new_calendar() -> Calendar:
    cal = icalendar.Calendar()
    cal.add("prodid", "-//caldav-mcp//caldav//EN")
    cal.add("version", "2.0")
    return cal


def _build_event_ical(
    summary: str,
    start_dt: datetime,
    end_dt: datetime,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    cal = _new_calendar()
    event = Event()
    event.add("uid", str(uuid.uuid4()))
    event.add("summary", summary)
    event.add("dtstart", start_dt)
    event.add("dtend", end_dt)
    event.add("dtstamp", datetime.now(UTC))
    if description:
        event.add("description", description)
    if location:
        event.add("location", location)
    cal.add_component(event)
    return cal.to_ical().decode("utf-8")


def _build_todo_ical(
    summary: str,
    description: Optional[str] = None,
    due: Any = None,
    status: str = "NEEDS-ACTION",
) -> str:
    cal = _new_calendar()
    todo = Todo()
    todo.add("uid", str(uuid.uuid4()))
    todo.add("summary", summary)
    todo.add("status", status.upper() if isinstance(status, str) else "NEEDS-ACTION")
    now = datetime.now(UTC)
    todo.add("dtstamp", now)
    todo.add("created", now)
    if description:
        todo.add("description", description)
    if due is not None:
        todo.add("due", due)
    cal.add_component(todo)
    return cal.to_ical().decode("utf-8")


@mcp.resource("config://instructions")
def caldav_instructions() -> str:
    # Custom instructions for claude on how to deal with timezones and date formats
    return f"""# CalDAV MCP Time Handling Instructions

## TIMEZONE POLICY (CLIENT-SUPPLIED)
- This server runs remotely and does NOT know your timezone automatically. YOU must supply it.
- **Pass your timezone to every datetime tool** via the `timezone` parameter (IANA name, e.g. `"America/Denver"`, `"UTC"`, `"Europe/Berlin"`).
- Datetime inputs are interpreted as **the user's local wall-clock time** in that timezone: "YYYY-MM-DD HH:MM"
- All-day events/todos use format: "YYYY-MM-DD"
- The server stores everything in UTC internally and returns times back to you in the timezone you supplied.
- If `timezone` is omitted, the server falls back to the `CALDAV_TIMEZONE` env var, else UTC.

## EVENT PARAMETERS
```
timezone: "America/Denver" (required - user's IANA timezone)
start_datetime: "YYYY-MM-DD HH:MM" (user's local time)
end_datetime: "YYYY-MM-DD HH:MM" (user's local time)
summary: "Event Title"
description: "Day - Designation - Uniform" (optional)
location: "Location Name" (optional)
```

## TODO PARAMETERS
```
timezone: "America/Denver" (required - user's IANA timezone)
due_date: "YYYY-MM-DD" (all-day) or "YYYY-MM-DD HH:MM" (timed, user's local time)
all_day: true/false (default true)
```

## OUTPUT
- All times returned by the server are shown in the timezone you supplied and labelled with the zone (e.g. `2026-08-11 06:45 MDT`).
- Events are sorted chronologically. Date filters are applied and respected.

**REMEMBER**: For every calendar/todo tool call, include the `timezone` parameter matching the user's location. Just pass times as they appear in source documents (e.g. `06:45` Mountain Time on Aug 11 -> `2026-08-11 06:45` with `timezone: "America/Denver"`). The server handles the timezone conversion automatically."""


@mcp.prompt(
    name="calendar_workflow",
    description=(
        "Comprehensive guidance for managing this user's course calendars: "
        "Mountain-Time input rule, per-course conventions, assessment naming, "
        "and known tool bugs. Load this prompt before doing calendar work."
    ),
)
def calendar_workflow() -> str:
    # Custom instructions for agents that manage the user's academic calendars.
    return """# CalDAV Calendar Workflow — Fall 2026 Academic Calendars

## 1. TIMEZONE RULE (CRITICAL)
- Input every start/end/due time as **MOUNTAIN TIME WALL-CLOCK** (America/Denver).
  NEVER pre-convert to UTC. The server converts to UTC for storage and the user's
  client renders back in Mountain time.
- Example: a 7:30 AM class is entered as `07:30` — NOT `13:30`. Entering `13:30`
  makes the event display at 1:30 PM (this broke 58 events once).
- Optionally pass `timezone: "America/Denver"` to make intent explicit; it is
  harmless. Plain Mountain wall-clock times are the verified working convention.

## 2. FORMATS
- Timed events: `YYYY-MM-DD HH:MM` (24h). All-day todos: `YYYY-MM-DD`.
- Todos default to all-day. Use all-day todos for readings/homework/labs.

## 3. CALENDAR LAYOUT
- `Academic Calendar`: master schedule (class sessions, M-day/T-day markers,
  holidays) — READ-ONLY, never modify; use as the source of session dates.
- Per-class calendars: `COMPSCI 210`, `ECE 245`, `PHYSICS 215`, `ECE 215S`,
  `CHINESE 221`, `PHYED 484B`, `SOCSCI 311`.
- `Tests and Quizzes`: ALL graded assessments for all courses as timed events.
- `Personal`, `Squadron`, `Bookings`, `Birthdays`, `Financial`: leave alone.

## 4. COURSE CONVENTIONS
- COMPSCI 210: 41 lesson events `Lsn N: <topic>` at 07:30-09:23; 17 named
  assignment todos; assessments `Quiz 1`-`Quiz 10`, `PA1`-`PA4`,
  `PEX1/2 written defense`, `Team PEX due / presentations` (unprefixed, legacy).
- ECE 245: NO lesson events; todos only — `Reading: <source> (<topic>)`,
  `HW H1`-`H24`, `Lab N: <topic>` + `Multisim take-home`. Assessments are
  course-prefixed: `ECE 245 Quiz 1`-`6`, `ECE 245 GR 1` (Sep 14), `GR 2` (Oct 30),
  `GR 3` (Dec 4). GRs and quizzes are both timed tests at the class slot (07:30).
- In the shared `Tests and Quizzes` calendar, always prefix assessments with the
  course name (except existing COMPSCI 210 items).

## 5. ADDING A NEW COURSE
1. Extract the syllabus (PDFs via `pdftotext -layout`; HTML read directly).
2. Pull that course's sessions from `Academic Calendar` -> assign lesson dates
   (lesson N maps to the Nth session chronologically).
3. Confirm/create the per-course calendar.
4. GRs/quizzes/exams -> timed events in `Tests and Quizzes`, course-prefixed,
   at the class slot time.
5. Readings -> all-day todos in the course calendar, due on the lesson day.
6. Homework/labs -> all-day todos with due dates; note assigned lesson/date in
   the description.
7. Re-fetch to verify counts and times.

## 6. KNOWN TOOL BUGS
- `create_calendar_events` (batch) is BROKEN ('str' object has no attribute
  'tzinfo'). Create events ONE AT A TIME with `create_calendar_event`.
- `create_todos` (batch) WORKS — batch in groups of ~10.
- update/delete match by EXACT summary — copy it from the get output.
- `get_calendar_events` shows a `+00:00` (UTC) suffix — ignore it; judge by
  wall-clock digits only, the client renders Mountain time."""


@mcp.tool(
    name="get_calendar_info",
    description="Get detailed information about a specific calendar",
)
def get_calendar_info(
    calendar_name: str = Field(
        ..., description="Name of the calendar to get information about"
    )
):
    """Tool to get detailed information about a specific calendar."""
    try:
        calendar = _find_calendar(calendar_name)
        events = calendar.events()
        event_count = len(events) if events else 0
        return (
            f"Calendar '{calendar_name}' info: {event_count} events, "
            f"URL: {calendar.url}, Display name: {calendar.get_display_name()}"
        )
    except Exception as e:
        return f"Error getting calendar info: {str(e)}"


@mcp.tool()
def get_calendars():
    """Tool to get a list of calendars with their content types."""
    try:
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return "No calendars found."

        calendar_list = []
        for calendar in calendars:
            try:
                events = calendar.events()
                todos = calendar.todos()
                event_count = len(events) if events else 0
                todo_count = len(todos) if todos else 0
                supported = calendar.get_supported_components()
                calendar_list.append(
                    f"{calendar.name} - Events: {event_count}, Todos: {todo_count} "
                    f"(Supports: {', '.join(supported)})"
                )
            except Exception as e:
                calendar_list.append(f"{calendar.name} - Error: {str(e)}")

        return "Available calendars:\n" + "\n".join(calendar_list)
    except Exception as e:
        return f"Error retrieving calendars: {str(e)}"


@mcp.tool(name="get_calendar_capabilities")
def get_calendar_capabilities(calendar_name: str):
    """Get what types of components (events, todos) a calendar supports."""
    try:
        calendar = _find_calendar(calendar_name)
        supported = calendar.get_supported_components()
        return f"Calendar '{calendar_name}' supports: {', '.join(supported)}"
    except Exception as e:
        return f"Error checking capabilities: {str(e)}"


@mcp.tool(
    name="get_calendar_events",
    description=(
        "Get events from a specific or all calendars. Results are date-filtered, "
        "sorted chronologically, and all times are shown in local time."
    ),
)
def get_calendar_events(
    calendar_name: Optional[str] = Field(
        None,
        description="Name of the calendar to get events from (optional: gets from all if omitted)",
    ),
    start_date: Optional[str] = Field(
        None, description="Start date for events (YYYY-MM-DD format)"
    ),
    end_date: Optional[str] = Field(
        None, description="End date for events (YYYY-MM-DD format)"
    ),
    limit: Optional[int] = Field(10, description="Maximum number of events to return"),
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name of the user (e.g. 'America/Denver') used for date filtering and formatting output times",
    ),
):
    """Get events from a specific calendar or all calendars, with optional date filtering."""
    try:
        principal = client.principal()
        calendars = principal.calendars()
        tz = resolve_tz(timezone)

        start = parse_date(start_date) if start_date else None
        end = parse_date(end_date) if end_date else None

        if calendar_name:
            calendar = next((cal for cal in calendars if cal.name == calendar_name), None)
            if not calendar:
                return f"Calendar '{calendar_name}' not found."
            calendars = [calendar]

        results = []

        for calendar in calendars:
            # Use a server-side time-range search when both bounds are given,
            # otherwise fetch everything and filter client-side.
            if start and end:
                events = calendar.search(
                    start=day_start(start, tz),
                    end=day_after(end, tz),
                    comp_class=caldav.Event,
                )
            else:
                events = calendar.events()

            for event in events:
                try:
                    comp = event.icalendar_component
                    summary = str(comp.get("summary")) if "summary" in comp else "No title"
                    description = (
                        str(comp.get("description"))
                        if "description" in comp
                        else "No description"
                    )
                    start_val = comp.get("dtstart").dt if "dtstart" in comp else None
                    end_val = comp.get("dtend").dt if "dtend" in comp else None

                    start_utc = to_utc(start_val, tz)
                    if start_utc is None:
                        continue

                    if not (start and end):
                        if start and start_utc < day_start(start, tz):
                            continue
                        if end and start_utc >= day_after(end, tz):
                            continue

                    results.append(
                        (
                            start_utc,
                            f"{summary} (from: {calendar.name}, "
                            f"{format_dt(start_val, tz)} - {format_dt(end_val, tz)})",
                        )
                    )
                except Exception as e:
                    results.append(
                        (
                            datetime.max.replace(tzinfo=UTC),
                            f"Error parsing event from {calendar.name}: {str(e)}",
                        )
                    )

        results.sort(key=lambda r: r[0])
        event_list = [text for _, text in results]
        if limit is not None:
            event_list = event_list[:limit]

        if not event_list:
            source = f"calendar '{calendar_name}'" if calendar_name else "any calendar"
            return f"No events found in {source}."

        prefix = (
            f"Events in '{calendar_name}' ({len(event_list)} found): "
            if calendar_name
            else f"Events from all calendars ({len(event_list)} found): "
        )
        return prefix + "; ".join(event_list)
    except Exception as e:
        return f"Error retrieving events: {str(e)}"


@mcp.tool(name="create_calendar_event", description="Create a new event in a calendar")
def create_calendar_event(
    calendar_name: str = Field(
        ..., description="Name of the calendar to add the event to"
    ),
    summary: str = Field(..., description="Title/summary of the event"),
    start_datetime: str = Field(
        ..., description="Start date and time (YYYY-MM-DD HH:MM in local time)"
    ),
    end_datetime: str = Field(
        ..., description="End date and time (YYYY-MM-DD HH:MM in local time)"
    ),
    description: Optional[str] = Field(None, description="Description of the event"),
    location: Optional[str] = Field(None, description="Location of the event"),
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name of the user (e.g. 'America/Denver') that start_datetime/end_datetime are in",
    ),
):
    """Create a new event in a specific calendar. Times are in the user's local timezone."""
    try:
        calendar = _find_calendar(calendar_name)
        tz = resolve_tz(timezone)

        start_dt = parse_dt_local(start_datetime, tz)
        end_dt = parse_dt_local(end_datetime, tz)
        if end_dt <= start_dt:
            return "Error creating event: end_datetime must be after start_datetime."

        ical = _build_event_ical(
            summary=summary,
            start_dt=start_dt,
            end_dt=end_dt,
            description=description,
            location=location,
        )
        calendar.save_event(ical)
        return (
            f"Event '{summary}' created successfully in calendar '{calendar_name}' "
            f"({format_dt(start_dt, tz)} - {format_dt(end_dt, tz)})"
        )
    except ValueError as e:
        return f"Error parsing datetime format: {str(e)}. Please use YYYY-MM-DD HH:MM format (local time)."
    except Exception as e:
        return f"Error creating event: {str(e)}"


@mcp.tool(
    name="create_calendar_events",
    description="Create multiple events in a specific calendar in batch. Times are interpreted as local time.",
)
def create_calendar_events(
    calendar_name: str = Field(..., description="Name of the target calendar"),
    events: List[Dict[str, Any]] = Field(
        ..., description=(
            "List of events. Each item must include: "
            "summary, start_datetime (YYYY-MM-DD HH:MM), end_datetime (YYYY-MM-DD HH:MM). "
            "Times are in the user's local timezone (see timezone param). "
            "Optional: description, location."
        )
    ),
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name of the user (e.g. 'America/Denver') that the event times are in",
    ),
) -> Dict[str, List[str]]:
    """Create multiple events in a given calendar. Returns success/errors lists."""
    results = {"success": [], "errors": []}

    try:
        calendar = _find_calendar(calendar_name)
        tz = resolve_tz(timezone)

        for idx, evt in enumerate(events, start=1):
            try:
                summary = evt.get("summary")
                start_str = evt.get("start_datetime")
                end_str = evt.get("end_datetime")
                description = evt.get("description")
                location = evt.get("location")

                if not summary or not start_str or not end_str:
                    raise ValueError(
                        "Missing one of: summary, start_datetime, end_datetime"
                    )

                try:
                    start_dt = parse_dt_local(start_str, tz)
                    end_dt = parse_dt_local(end_str, tz)
                except ValueError:
                    raise ValueError("Invalid datetime format. Use 'YYYY-MM-DD HH:MM' (local time).")

                if end_dt <= start_dt:
                    raise ValueError("end_datetime must be after start_datetime")

                ical = _build_event_ical(
                    summary=summary,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    description=description,
                    location=location,
                )
                calendar.save_event(ical)
                results["success"].append(
                    f"[Event #{idx}] '{summary}' created successfully."
                )
            except Exception as e:
                results["errors"].append(
                    f"[Event #{idx}] {evt.get('summary', '<no summary>')}: {str(e)}"
                )

        return results
    except Exception as e:
        return {"success": [], "errors": [f"Batch creation failed: {str(e)}"]}


@mcp.tool(name="delete_calendar_event", description="Delete an event from a calendar")
def delete_calendar_event(
    calendar_name: str = Field(
        ..., description="Name of the calendar containing the event"
    ),
    event_summary: str = Field(..., description="Summary/title of the event to delete"),
):
    """Delete an event from a specific calendar by its summary."""
    try:
        calendar = _find_calendar(calendar_name)

        events = calendar.events()
        matching_events = []
        for event in events:
            try:
                comp = event.icalendar_component
                if "summary" in comp and str(comp.get("summary")) == event_summary:
                    matching_events.append(event)
            except Exception:
                continue

        if not matching_events:
            return f"No event found with summary '{event_summary}' in calendar '{calendar_name}'"

        if len(matching_events) > 1:
            return f"Multiple events found with summary '{event_summary}'. Please be more specific."

        matching_events[0].delete()
        return f"Event '{event_summary}' deleted successfully from calendar '{calendar_name}'"
    except Exception as e:
        return f"Error deleting event: {str(e)}"


@mcp.tool(
    name="update_calendar_event", description="Update an existing event in a calendar"
)
def update_calendar_event(
    calendar_name: str = Field(
        ..., description="Name of the calendar containing the event"
    ),
    event_summary: str = Field(
        ..., description="Current summary/title of the event to update"
    ),
    new_summary: Optional[str] = Field(
        None, description="New title/summary for the event"
    ),
    new_start_datetime: Optional[str] = Field(
        None, description="New start date and time (YYYY-MM-DD HH:MM in local time)"
    ),
    new_end_datetime: Optional[str] = Field(
        None, description="New end date and time (YYYY-MM-DD HH:MM in local time)"
    ),
    new_description: Optional[str] = Field(
        None, description="New description for the event"
    ),
    new_location: Optional[str] = Field(None, description="New location for the event"),
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name of the user (e.g. 'America/Denver') that the new datetimes are in",
    ),
):
    """Update an existing event in a specific calendar. Times are in the user's local timezone."""
    try:
        calendar = _find_calendar(calendar_name)
        tz = resolve_tz(timezone)

        events = calendar.events()
        matching_events = []
        for event in events:
            try:
                comp = event.icalendar_component
                if "summary" in comp and str(comp.get("summary")) == event_summary:
                    matching_events.append(event)
            except Exception:
                continue

        if not matching_events:
            return f"No event found with summary '{event_summary}' in calendar '{calendar_name}'"

        if len(matching_events) > 1:
            return f"Multiple events found with summary '{event_summary}'. Please be more specific."

        event = matching_events[0]
        comp = event.icalendar_component

        if new_summary:
            comp["summary"] = new_summary
        if new_start_datetime:
            comp.pop("dtstart")
            comp.add("dtstart", parse_dt_local(new_start_datetime, tz))
        if new_end_datetime:
            comp.pop("dtend")
            comp.add("dtend", parse_dt_local(new_end_datetime, tz))
        if new_description is not None:
            comp.pop("description", None)
            comp.add("description", new_description)
        if new_location is not None:
            comp.pop("location", None)
            comp.add("location", new_location)

        event.icalendar_component = comp
        event.save()

        return f"Event '{event_summary}' updated successfully in calendar '{calendar_name}'"
    except ValueError as e:
        return f"Error parsing datetime format: {str(e)}. Please use YYYY-MM-DD HH:MM format (local time)."
    except Exception as e:
        return f"Error updating event: {str(e)}"


@mcp.tool(
    name="search_calendar_events", description="Search for events across all calendars"
)
def search_calendar_events(
    query: str = Field(
        ..., description="Search term to look for in event summaries and descriptions"
    ),
    start_date: Optional[str] = Field(
        None, description="Start date for search (YYYY-MM-DD format)"
    ),
    end_date: Optional[str] = Field(
        None, description="End date for search (YYYY-MM-DD format)"
    ),
    limit: Optional[int] = Field(10, description="Maximum number of events to return"),
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name of the user (e.g. 'America/Denver') used for date filtering and formatting output times",
    ),
):
    """Search for events across all calendars, with optional date filtering."""
    try:
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return "No calendars found."
        tz = resolve_tz(timezone)

        start = parse_date(start_date) if start_date else None
        end = parse_date(end_date) if end_date else None

        matching_events = []

        for calendar in calendars:
            try:
                events = calendar.events()
                for event in events:
                    try:
                        comp = event.icalendar_component
                        summary = str(comp.get("summary")) if "summary" in comp else ""
                        description = (
                            str(comp.get("description"))
                            if "description" in comp
                            else ""
                        )
                        start_val = (
                            comp.get("dtstart").dt if "dtstart" in comp else None
                        )
                        start_utc = to_utc(start_val, tz)

                        if start_utc is not None:
                            if start and start_utc < day_start(start, tz):
                                continue
                            if end and start_utc >= day_after(end, tz):
                                continue

                        if (
                            query.lower() in summary.lower()
                            or query.lower() in description.lower()
                        ):
                            matching_events.append(
                                {
                                    "calendar": calendar.name,
                                    "summary": summary,
                                    "start": format_dt(start_val, tz),
                                    "description": (
                                        description[:100] + "..."
                                        if len(description) > 100
                                        else description
                                    ),
                                }
                            )

                            if limit and len(matching_events) >= limit:
                                break
                    except Exception:
                        continue

                if limit and len(matching_events) >= limit:
                    break
            except Exception:
                continue

        if not matching_events:
            return f"No events found matching '{query}'"

        result = f"Found {len(matching_events)} events matching '{query}':\n"
        for event in matching_events:
            result += f"- {event['summary']} in {event['calendar']} ({event['start']})\n"
        return result
    except Exception as e:
        return f"Error searching events: {str(e)}"


@mcp.tool(name="create_calendar", description="Create a new calendar")
def create_calendar(
    calendar_name: str = Field(..., description="Name for the new calendar"),
    display_name: Optional[str] = Field(
        None, description="Display name for the calendar"
    ),
):
    """Create a new calendar."""
    try:
        principal = client.principal()
        existing = principal.calendars()
        if any(cal.name == calendar_name for cal in existing):
            return f"Calendar '{calendar_name}' already exists."

        principal.make_calendar(name=calendar_name, cal_id=display_name or calendar_name)
        return f"Calendar '{calendar_name}' created successfully."
    except Exception as e:
        return f"Error creating calendar: {str(e)}"


@mcp.tool(
    name="get_todos",
    description="Get todos from a specific or all calendars, annotating calendar names",
)
def get_todos(
    calendar_name: Optional[str] = Field(
        None,
        description="Name of the calendar to get todos from (optional: gets from all if omitted)",
    ),
    status: Optional[str] = Field(
        None,
        description="Filter by status: NEEDS-ACTION, COMPLETED, IN-PROCESS, CANCELLED",
    ),
    limit: Optional[int] = Field(10, description="Maximum number of todos to return"),
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name of the user (e.g. 'America/Denver') used to format due dates in output",
    ),
):
    """Get todos from a specific or all calendars, with optional status filtering."""
    try:
        principal = client.principal()
        calendars = principal.calendars()
        tz = resolve_tz(timezone)

        if calendar_name:
            calendar = next(
                (cal for cal in calendars if cal.name == calendar_name), None
            )
            if not calendar:
                return f"Calendar '{calendar_name}' not found."
            calendars = [calendar]

        todo_list = []
        total_todos = 0

        for calendar in calendars:
            todos = calendar.todos()
            for todo in todos:
                if limit and total_todos >= limit:
                    break

                try:
                    comp = todo.icalendar_component
                    summary = str(comp.get("summary")) if "summary" in comp else "No title"
                    todo_status = (
                        str(comp.get("status")) if "status" in comp else "NEEDS-ACTION"
                    )
                    due_val = comp.get("due").dt if "due" in comp else None
                    description = (
                        str(comp.get("description"))
                        if "description" in comp
                        else "No description"
                    )
                    completed = (
                        str(comp.get("completed"))
                        if "completed" in comp
                        else "Not completed"
                    )

                    if status and todo_status.upper() != status.upper():
                        continue

                    indicator = "✓" if todo_status == "COMPLETED" else "○"
                    todo_list.append(
                        f"{indicator} {summary} (from: {calendar.name}, "
                        f"Due: {format_dt(due_val, tz)}, Status: {todo_status})"
                    )
                    total_todos += 1
                except Exception as e:
                    todo_list.append(f"Error parsing todo from {calendar.name}: {str(e)}")
                    total_todos += 1

        if not todo_list:
            source = f"calendar '{calendar_name}'" if calendar_name else "any calendar"
            return f"No todos found in {source}."

        prefix = (
            f"Todos in '{calendar_name}' ({len(todo_list)} found): "
            if calendar_name
            else f"Todos from all calendars ({total_todos} found): "
        )
        return prefix + "; ".join(todo_list)
    except Exception as e:
        return f"Error retrieving todos: {str(e)}"


@mcp.tool(name="create_todo", description="Create a new todo in a calendar")
def create_todo(
    calendar_name: str = Field(
        ..., description="Name of the calendar to add the todo to"
    ),
    summary: str = Field(..., description="Title/summary of the todo"),
    description: Optional[str] = Field(None, description="Description of the todo"),
    due_date: Optional[str] = Field(
        None,
        description="Due date: YYYY-MM-DD for all-day, YYYY-MM-DD HH:MM (local time) for timed",
    ),
    all_day: Optional[bool] = Field(
        True, description="Whether the todo is all-day (default: True)"
    ),
    status: Optional[str] = Field(
        "NEEDS-ACTION",
        description="Status: NEEDS-ACTION, IN-PROCESS, COMPLETED, CANCELLED",
    ),
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name of the user (e.g. 'America/Denver') that due_date is in",
    ),
):
    """Create a new todo in a specific calendar. Supports all-day and timed todos."""
    try:
        calendar = _find_calendar(calendar_name)
        tz = resolve_tz(timezone)

        due = None
        if due_date:
            try:
                if all_day:
                    due = parse_date(due_date.split()[0])
                else:
                    due = parse_dt_local(due_date, tz)
            except ValueError as e:
                return (
                    f"Error parsing date format: {due_date}. "
                    f"Use YYYY-MM-DD for all-day or YYYY-MM-DD HH:MM (local time) for timed. "
                    f"Error: {str(e)}"
                )

        ical = _build_todo_ical(
            summary=summary,
            description=description,
            due=due,
            status=status or "NEEDS-ACTION",
        )
        calendar.save_event(ical)

        todo_type = "all-day" if all_day else "timed"
        return f"Todo '{summary}' created successfully as {todo_type} in calendar '{calendar_name}'"
    except Exception as e:
        return f"Error creating todo: {str(e)}"


@mcp.tool(
    name="create_todos",
    description="Create multiple todos in a specific calendar in batch.",
)
def create_todos(
    calendar_name: str = Field(..., description="The name of the target calendar"),
    todos: List[Dict[str, Any]] = Field(
        ..., description="A list of todos, each with summary, optional description, due_date, etc."
    ),
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name of the user (e.g. 'America/Denver') that the due dates are in",
    ),
) -> Dict[str, Any]:
    """Create multiple todos in a given calendar. Returns success/errors lists."""
    results = {"success": [], "errors": []}

    try:
        calendar = _find_calendar(calendar_name)
        tz = resolve_tz(timezone)

        for idx, todo_data in enumerate(todos, start=1):
            try:
                summary = todo_data.get("summary")
                if not summary:
                    raise ValueError("Missing required field: summary")

                description = todo_data.get("description")
                due_date = todo_data.get("due_date")
                all_day: bool = todo_data.get("all_day", True)
                status = todo_data.get("status", "NEEDS-ACTION")

                due = None
                if due_date:
                    try:
                        if all_day:
                            due = parse_date(due_date.split()[0])
                        else:
                            due = parse_dt_local(due_date, tz)
                    except ValueError as e:
                        raise ValueError(
                            f"Invalid date format for due_date '{due_date}': {str(e)}"
                        )

                ical = _build_todo_ical(
                    summary=summary,
                    description=description,
                    due=due,
                    status=status,
                )
                calendar.save_event(ical)
                todo_type = "all-day" if all_day else "timed"
                results["success"].append(
                    f"Todo '{summary}' created successfully as {todo_type}."
                )
            except Exception as e:
                results["errors"].append(
                    f"[Todo #{idx}] {todo_data.get('summary', '<no summary>')}: {str(e)}"
                )

        return results
    except Exception as e:
        return {"success": [], "errors": [f"Batch creation failed: {str(e)}"]}


@mcp.tool(name="update_todo", description="Update an existing todo in a calendar")
def update_todo(
    calendar_name: str = Field(
        ..., description="Name of the calendar containing the todo"
    ),
    todo_summary: str = Field(
        ..., description="Current summary/title of the todo to update"
    ),
    new_summary: Optional[str] = Field(
        None, description="New title/summary for the todo"
    ),
    new_description: Optional[str] = Field(
        None, description="New description for the todo"
    ),
    new_due_date: Optional[str] = Field(
        None, description="New due date: YYYY-MM-DD or YYYY-MM-DD HH:MM (local time)"
    ),
    new_status: Optional[str] = Field(
        None, description="New status: NEEDS-ACTION, IN-PROCESS, COMPLETED, CANCELLED"
    ),
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name of the user (e.g. 'America/Denver') that new_due_date is in",
    ),
):
    """Update an existing todo in a specific calendar."""
    try:
        calendar = _find_calendar(calendar_name)
        tz = resolve_tz(timezone)

        todos = calendar.todos()
        matching_todos = []
        for todo in todos:
            try:
                comp = todo.icalendar_component
                if "summary" in comp and str(comp.get("summary")) == todo_summary:
                    matching_todos.append(todo)
            except Exception:
                continue

        if not matching_todos:
            return f"No todo found with summary '{todo_summary}' in calendar '{calendar_name}'"

        if len(matching_todos) > 1:
            return f"Multiple todos found with summary '{todo_summary}'. Please be more specific."

        todo = matching_todos[0]
        comp = todo.icalendar_component

        if new_summary:
            comp["summary"] = new_summary
        if new_description is not None:
            comp.pop("description", None)
            comp.add("description", new_description)
        if new_due_date:
            comp.pop("due")
            comp.add("due", parse_due(new_due_date, tz))
        if new_status:
            comp["status"] = new_status.upper()
            if new_status.upper() == "COMPLETED":
                comp["completed"] = datetime.now(UTC)

        todo.icalendar_component = comp
        todo.save()

        return f"Todo '{todo_summary}' updated successfully in calendar '{calendar_name}'"
    except ValueError as e:
        return f"Error parsing date format: {str(e)}. Use YYYY-MM-DD or YYYY-MM-DD HH:MM (local time)."
    except Exception as e:
        return f"Error updating todo: {str(e)}"


@mcp.tool(name="delete_todo", description="Delete a todo from a calendar")
def delete_todo(
    calendar_name: str = Field(
        ..., description="Name of the calendar containing the todo"
    ),
    todo_summary: str = Field(..., description="Summary/title of the todo to delete"),
):
    """Delete a todo from a specific calendar by its summary."""
    try:
        calendar = _find_calendar(calendar_name)

        todos = calendar.todos()
        matching_todos = []
        for todo in todos:
            try:
                comp = todo.icalendar_component
                if "summary" in comp and str(comp.get("summary")) == todo_summary:
                    matching_todos.append(todo)
            except Exception:
                continue

        if not matching_todos:
            return f"No todo found with summary '{todo_summary}' in calendar '{calendar_name}'"

        if len(matching_todos) > 1:
            return f"Multiple todos found with summary '{todo_summary}'. Please be more specific."

        matching_todos[0].delete()
        return f"Todo '{todo_summary}' deleted successfully from calendar '{calendar_name}'"
    except Exception as e:
        return f"Error deleting todo: {str(e)}"


@mcp.tool(name="complete_todo", description="Mark a todo as completed")
def complete_todo(
    calendar_name: str = Field(
        ..., description="Name of the calendar containing the todo"
    ),
    todo_summary: str = Field(..., description="Summary/title of the todo to complete"),
):
    """Mark a todo as completed."""
    try:
        calendar = _find_calendar(calendar_name)

        todos = calendar.todos()
        matching_todos = []
        for todo in todos:
            try:
                comp = todo.icalendar_component
                if "summary" in comp and str(comp.get("summary")) == todo_summary:
                    matching_todos.append(todo)
            except Exception:
                continue

        if not matching_todos:
            return f"No todo found with summary '{todo_summary}' in calendar '{calendar_name}'"

        if len(matching_todos) > 1:
            return f"Multiple todos found with summary '{todo_summary}'. Please be more specific."

        todo = matching_todos[0]
        comp = todo.icalendar_component
        comp["status"] = "COMPLETED"
        comp["completed"] = datetime.now(UTC)

        todo.icalendar_component = comp
        todo.save()

        return f"Todo '{todo_summary}' marked as completed in calendar '{calendar_name}'"
    except Exception as e:
        return f"Error completing todo: {str(e)}"


@mcp.tool(name="search_todos", description="Search for todos across all calendars")
def search_todos(
    query: str = Field(
        ..., description="Search term to look for in todo summaries and descriptions"
    ),
    status: Optional[str] = Field(
        None,
        description="Filter by status: NEEDS-ACTION, COMPLETED, IN-PROCESS, CANCELLED",
    ),
    limit: Optional[int] = Field(10, description="Maximum number of todos to return"),
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone name of the user (e.g. 'America/Denver') used to format due dates in output",
    ),
):
    """Search for todos across all calendars, with optional status filtering."""
    try:
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return "No calendars found."
        tz = resolve_tz(timezone)

        matching_todos = []

        for calendar in calendars:
            try:
                todos = calendar.todos()
                for todo in todos:
                    try:
                        comp = todo.icalendar_component
                        summary = str(comp.get("summary")) if "summary" in comp else ""
                        description = (
                            str(comp.get("description"))
                            if "description" in comp
                            else ""
                        )
                        todo_status = (
                            str(comp.get("status")) if "status" in comp else "NEEDS-ACTION"
                        )
                        due_val = comp.get("due").dt if "due" in comp else None

                        if status and todo_status.upper() != status.upper():
                            continue

                        if (
                            query.lower() in summary.lower()
                            or query.lower() in description.lower()
                        ):
                            indicator = "✓" if todo_status == "COMPLETED" else "○"
                            matching_todos.append(
                                {
                                    "calendar": calendar.name,
                                    "summary": summary,
                                    "status": todo_status,
                                    "due": format_dt(due_val, tz),
                                    "indicator": indicator,
                                    "description": (
                                        description[:100] + "..."
                                        if len(description) > 100
                                        else description
                                    ),
                                }
                            )

                            if limit and len(matching_todos) >= limit:
                                break
                    except Exception:
                        continue

                if limit and len(matching_todos) >= limit:
                    break
            except Exception:
                continue

        if not matching_todos:
            return f"No todos found matching '{query}'"

        result = f"Found {len(matching_todos)} todos matching '{query}':\n"
        for todo in matching_todos:
            result += (
                f"- {todo['indicator']} {todo['summary']} in {todo['calendar']} "
                f"(Due: {todo['due']}, Status: {todo['status']})\n"
            )
        return result
    except Exception as e:
        return f"Error searching todos: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="sse")
