import caldav
from datetime import datetime
from dotenv import load_dotenv
import os
import uuid
from typing import Optional
import vobject

from mcp.server.fastmcp import FastMCP
from pydantic import Field


load_dotenv()

CALDAV_URL = os.getenv("CALDAV_URL", "https://caldav.example.com")
CALDAV_USERNAME = os.getenv("CALDAV_USERNAME", "John Doe")
CALDAV_PASSWORD = os.getenv("CALDAV_PASSWORD", "password123")

client = caldav.DAVClient(
    url=CALDAV_URL, username=CALDAV_USERNAME, password=CALDAV_PASSWORD
)

mcp = FastMCP(
    "CalDAV Server",
    instructions="This is a CalDAV server. Use the tools provided to interact with your calendars and todos",
)


@mcp.tool(
    name="get_calendar_info",
    description="Get detailed information about a specific calendar",
)
def get_calendar_info(
    calendar_name: str = Field(
        ..., description="Name of the calendar to get information about"
    )
):
    """
    Tool to get detailed information about a specific calendar.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()
        calendar = next((cal for cal in calendars if cal.name == calendar_name), None)

        if not calendar:
            return f"Calendar '{calendar_name}' not found."

        # Get calendar properties
        events = calendar.events()
        event_count = len(events) if events else 0

        info = {
            "name": calendar.name,
            "url": str(calendar.url),
            "display_name": getattr(
                calendar, "get_display_name", lambda: calendar.name
            )(),
            "event_count": event_count,
            "supported_components": getattr(
                calendar, "get_supported_components", lambda: ["VEVENT"]
            )(),
        }

        return (
            f"Calendar '{calendar_name}' info: {event_count} events, URL: {info['url']}"
        )
    except Exception as e:
        return f"Error getting calendar info: {str(e)}"


@mcp.tool()
def get_calendars():
    """
    Tool to get a list of calendars with their content types.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return "No calendars found."

        calendar_list = []
        for calendar in calendars:
            try:
                # Get counts
                events = calendar.events()
                todos = calendar.todos()
                event_count = len(events) if events else 0
                todo_count = len(todos) if todos else 0

                # Get supported components
                supported = calendar.get_supported_components()

                calendar_info = (
                    f"{calendar.name} - Events: {event_count}, Todos: {todo_count} "
                    f"(Supports: {', '.join(supported)})"
                )
                calendar_list.append(calendar_info)
            except Exception as e:
                calendar_list.append(f"{calendar.name} - Error: {str(e)}")

        return "Available calendars:\n" + "\n".join(calendar_list)
    except Exception as e:
        return f"Error retrieving calendars: {str(e)}"


@mcp.tool(name="get_calendar_capabilities")
def get_calendar_capabilities(calendar_name: str):
    """
    Get what types of components (events, todos) a calendar supports.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()
        calendar = next((cal for cal in calendars if cal.name == calendar_name), None)

        if not calendar:
            return f"Calendar '{calendar_name}' not found."

        # Check supported components
        supported = calendar.get_supported_components()

        capabilities = {
            "supports_events": "VEVENT" in supported,
            "supports_todos": "VTODO" in supported,
            "all_components": supported,
        }

        return f"Calendar '{calendar_name}' supports: {', '.join(supported)}"
    except Exception as e:
        return f"Error checking capabilities: {str(e)}"


from typing import Optional
from datetime import datetime


@mcp.tool(
    name="get_calendar_events",
    description="Get events from specific or all calendars, annotating calendar names",
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
):
    """
    Tool to get events from a specific calendar or all calendars, with optional date filtering.
    Each event is annotated with its calendar name.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()

        # Set date range if provided
        start_dt = None
        end_dt = None
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        event_list = []
        total_events = 0

        # If calendar_name is provided, filter for that calendar only
        if calendar_name:
            calendar = next(
                (cal for cal in calendars if cal.name == calendar_name), None
            )
            if not calendar:
                return f"Calendar '{calendar_name}' not found."
            calendars = [calendar]

        for calendar in calendars:
            cal_name = calendar.name
            # Get events with optional date filtering
            if start_dt and end_dt:
                events = calendar.date_search(start=start_dt, end=end_dt)
            else:
                events = calendar.events()

            for i, event in enumerate(events):
                if limit and total_events >= limit:
                    break

                try:
                    vevent = event.vobject_instance.vevent  # type: ignore
                    summary = getattr(vevent, "summary", None)
                    dtstart = getattr(vevent, "dtstart", None)
                    dtend = getattr(vevent, "dtend", None)
                    description = getattr(vevent, "description", None)

                    event_info = {
                        "summary": summary.value if summary else "No title",
                        "start": str(dtstart.value) if dtstart else "No start time",
                        "end": str(dtend.value) if dtend else "No end time",
                        "description": (
                            description.value if description else "No description"
                        ),
                        "calendar": cal_name,
                    }

                    event_list.append(
                        f"{event_info['summary']} (from: {event_info['calendar']}, {event_info['start']} - {event_info['end']})"
                    )
                    total_events += 1
                except Exception as e:
                    event_list.append(f"Error parsing event from {cal_name}: {str(e)}")
                    total_events += 1

        if not event_list:
            if calendar_name:
                return f"No events found in calendar '{calendar_name}'."
            else:
                return "No events found in any calendar."

        if calendar_name:
            return (
                f"Events in '{calendar_name}' ({len(event_list)} found): "
                + "; ".join(event_list)
            )
        else:
            return f"Events from all calendars ({total_events} found): " + "; ".join(
                event_list
            )
    except Exception as e:
        return f"Error retrieving events: {str(e)}"


@mcp.tool(name="create_calendar_event", description="Create a new event in a calendar")
def create_calendar_event(
    calendar_name: str = Field(
        ..., description="Name of the calendar to add the event to"
    ),
    summary: str = Field(..., description="Title/summary of the event"),
    start_datetime: str = Field(
        ..., description="Start date and time (YYYY-MM-DD HH:MM format)"
    ),
    end_datetime: str = Field(
        ..., description="End date and time (YYYY-MM-DD HH:MM format)"
    ),
    description: Optional[str] = Field(None, description="Description of the event"),
    location: Optional[str] = Field(None, description="Location of the event"),
):
    """
    Tool to create a new event in a specific calendar.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()
        calendar = next((cal for cal in calendars if cal.name == calendar_name), None)

        if not calendar:
            return f"Calendar '{calendar_name}' not found."

        # Parse datetime strings
        start_dt = datetime.strptime(start_datetime, "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(end_datetime, "%Y-%m-%d %H:%M")

        # Create the event
        calendar.add_event(
            summary=summary,
            dtstart=start_dt,
            dtend=end_dt,
            description=description if description else None,
            location=location if location else None,
        )

        return f"Event '{summary}' created successfully in calendar '{calendar_name}'"
    except ValueError as e:
        return f"Error parsing datetime format: {str(e)}. Please use YYYY-MM-DD HH:MM format."
    except Exception as e:
        return f"Error creating event: {str(e)}"


@mcp.tool(name="delete_calendar_event", description="Delete an event from a calendar")
def delete_calendar_event(
    calendar_name: str = Field(
        ..., description="Name of the calendar containing the event"
    ),
    event_summary: str = Field(..., description="Summary/title of the event to delete"),
):
    """
    Tool to delete an event from a specific calendar by its summary.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()
        calendar = next((cal for cal in calendars if cal.name == calendar_name), None)

        if not calendar:
            return f"Calendar '{calendar_name}' not found."

        events = calendar.events()
        matching_events = []

        for event in events:
            try:
                vevent = event.vobject_instance.vevent  # type: ignore
                summary = getattr(vevent, "summary", None)
                if summary and summary.value == event_summary:
                    matching_events.append(event)
            except Exception:
                continue

        if not matching_events:
            return f"No event found with summary '{event_summary}' in calendar '{calendar_name}'"

        if len(matching_events) > 1:
            return f"Multiple events found with summary '{event_summary}'. Please be more specific."

        # Delete the event
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
        None, description="New start date and time (YYYY-MM-DD HH:MM format)"
    ),
    new_end_datetime: Optional[str] = Field(
        None, description="New end date and time (YYYY-MM-DD HH:MM format)"
    ),
    new_description: Optional[str] = Field(
        None, description="New description for the event"
    ),
    new_location: Optional[str] = Field(None, description="New location for the event"),
):
    """
    Tool to update an existing event in a specific calendar.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()
        calendar = next((cal for cal in calendars if cal.name == calendar_name), None)

        if not calendar:
            return f"Calendar '{calendar_name}' not found."

        events = calendar.events()
        matching_events = []

        for event in events:
            try:
                vevent = event.vobject_instance.vevent  # type: ignore
                summary = getattr(vevent, "summary", None)
                if summary and summary.value == event_summary:
                    matching_events.append(event)
            except Exception:
                continue

        if not matching_events:
            return f"No event found with summary '{event_summary}' in calendar '{calendar_name}'"

        if len(matching_events) > 1:
            return f"Multiple events found with summary '{event_summary}'. Please be more specific."

        # Update the event
        event = matching_events[0]
        vevent = event.vobject_instance.vevent

        if new_summary:
            vevent.summary.value = new_summary
        if new_start_datetime:
            vevent.dtstart.value = datetime.strptime(
                new_start_datetime, "%Y-%m-%d %H:%M"
            )
        if new_end_datetime:
            vevent.dtend.value = datetime.strptime(new_end_datetime, "%Y-%m-%d %H:%M")
        if new_description:
            if hasattr(vevent, "description"):
                vevent.description.value = new_description
            else:
                vevent.add("description").value = new_description
        if new_location:
            if hasattr(vevent, "location"):
                vevent.location.value = new_location
            else:
                vevent.add("location").value = new_location

        # Save the updated event
        event.save()

        return f"Event '{event_summary}' updated successfully in calendar '{calendar_name}'"
    except ValueError as e:
        return f"Error parsing datetime format: {str(e)}. Please use YYYY-MM-DD HH:MM format."
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
):
    """
    Tool to search for events across all calendars.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()

        if not calendars:
            return "No calendars found."

        matching_events = []

        for calendar in calendars:
            try:
                # Set date range if provided
                if start_date and end_date:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                    events = calendar.date_search(start=start_dt, end=end_dt)
                else:
                    events = calendar.events()

                for event in events:
                    try:
                        vevent = event.vobject_instance.vevent  # type: ignore
                        summary = getattr(vevent, "summary", None)
                        description = getattr(vevent, "description", None)
                        dtstart = getattr(vevent, "dtstart", None)

                        summary_text = summary.value if summary else ""
                        description_text = description.value if description else ""

                        if (
                            query.lower() in summary_text.lower()
                            or query.lower() in description_text.lower()
                        ):

                            matching_events.append(
                                {
                                    "calendar": calendar.name,
                                    "summary": summary_text,
                                    "start": (
                                        str(dtstart.value)
                                        if dtstart
                                        else "No start time"
                                    ),
                                    "description": (
                                        description_text[:100] + "..."
                                        if len(description_text) > 100
                                        else description_text
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
            result += (
                f"- {event['summary']} in {event['calendar']} ({event['start']})\n"
            )

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
    """
    Tool to create a new calendar.
    """
    try:
        principal = client.principal()

        # Check if calendar already exists
        existing_calendars = principal.calendars()
        if any(cal.name == calendar_name for cal in existing_calendars):
            return f"Calendar '{calendar_name}' already exists."

        # Create new calendar
        new_calendar = principal.make_calendar(
            name=calendar_name, cal_id=display_name or calendar_name
        )

        return f"Calendar '{calendar_name}' created successfully."
    except Exception as e:
        return f"Error creating calendar: {str(e)}"


from typing import Optional
from datetime import datetime


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
):
    """
    Tool to get todos from a specific or all calendars, with optional status filtering.
    Each todo is annotated with its calendar name.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()

        # If calendar_name is provided, filter for that calendar only
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
            cal_name = calendar.name
            todos = calendar.todos()

            for i, todo in enumerate(todos):
                if limit and total_todos >= limit:
                    break

                try:
                    vtodo = todo.vobject_instance.vtodo  # type: ignore
                    summary = getattr(vtodo, "summary", None)
                    todo_status = getattr(vtodo, "status", None)
                    due = getattr(vtodo, "due", None)
                    priority = getattr(vtodo, "priority", None)
                    description = getattr(vtodo, "description", None)
                    completed = getattr(vtodo, "completed", None)

                    # Filter by status if specified
                    if (
                        status
                        and todo_status
                        and todo_status.value.upper() != status.upper()
                    ):
                        continue

                    todo_info = {
                        "summary": summary.value if summary else "No title",
                        "status": todo_status.value if todo_status else "NEEDS-ACTION",
                        "due": str(due.value) if due else "No due date",
                        "priority": priority.value if priority else "No priority",
                        "description": (
                            description.value if description else "No description"
                        ),
                        "completed": (
                            str(completed.value) if completed else "Not completed"
                        ),
                        "calendar": cal_name,
                    }

                    status_indicator = (
                        "✓" if todo_info["status"] == "COMPLETED" else "○"
                    )
                    todo_list.append(
                        f"{status_indicator} {todo_info['summary']} (from: {todo_info['calendar']}, Due: {todo_info['due']}, Status: {todo_info['status']})"
                    )
                    total_todos += 1
                except Exception as e:
                    todo_list.append(f"Error parsing todo from {cal_name}: {str(e)}")
                    total_todos += 1

        if not todo_list:
            if calendar_name:
                return f"No todos found in calendar '{calendar_name}'."
            else:
                return "No todos found in any calendar."

        if calendar_name:
            return f"Todos in '{calendar_name}' ({len(todo_list)} found): " + "; ".join(
                todo_list
            )
        else:
            return f"Todos from all calendars ({total_todos} found): " + "; ".join(
                todo_list
            )
    except Exception as e:
        return f"Error retrieving todos: {str(e)}"


@mcp.tool(name="create_todo", description="Create a new todo in a calendar")
def create_todo(
    calendar_name: str = Field(
        ..., description="Name of the calendar to add the todo to"
    ),
    summary: str = Field(..., description="Title/summary of the todo"),
    description: Optional[str] = Field(None, description="Description of the todo"),
    due_date: Optional[str] = Field(None, description="Due date (YYYY-MM-DD format)"),
    priority: Optional[int] = Field(None, description="Priority (1=highest, 9=lowest)"),
    status: Optional[str] = Field(
        "NEEDS-ACTION",
        description="Status: NEEDS-ACTION, IN-PROCESS, COMPLETED, CANCELLED",
    ),
):
    """
    Tool to create a new todo in a specific calendar.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()
        calendar = next((cal for cal in calendars if cal.name == calendar_name), None)

        if not calendar:
            return f"Calendar '{calendar_name}' not found."

        # Create the todo
        todo = vobject.iCalendar()
        todo.add("vtodo")

        vtodo = todo.vtodo
        vtodo.add("uid").value = str(uuid.uuid4())
        vtodo.add("summary").value = summary
        vtodo.add("status").value = status.upper() if status else "NEEDS-ACTION"
        vtodo.add("dtstamp").value = datetime.now()
        vtodo.add("created").value = datetime.now()

        if description:
            vtodo.add("description").value = description
        if due_date:
            due_dt = datetime.strptime(due_date, "%Y-%m-%d")
            vtodo.add("due").value = due_dt
        if priority:
            vtodo.add("priority").value = priority

        # Save the todo
        calendar.save_event(todo.serialize())

        return f"Todo '{summary}' created successfully in calendar '{calendar_name}'"
    except ValueError as e:
        return f"Error parsing date format: {str(e)}. Please use YYYY-MM-DD format."
    except Exception as e:
        return f"Error creating todo: {str(e)}"


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
        None, description="New due date (YYYY-MM-DD format)"
    ),
    new_priority: Optional[int] = Field(
        None, description="New priority (1=highest, 9=lowest)"
    ),
    new_status: Optional[str] = Field(
        None, description="New status: NEEDS-ACTION, IN-PROCESS, COMPLETED, CANCELLED"
    ),
):
    """
    Tool to update an existing todo in a specific calendar.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()
        calendar = next((cal for cal in calendars if cal.name == calendar_name), None)

        if not calendar:
            return f"Calendar '{calendar_name}' not found."

        todos = calendar.todos()
        matching_todos = []

        for todo in todos:
            try:
                vtodo = todo.vobject_instance.vtodo  # type: ignore
                summary = getattr(vtodo, "summary", None)
                if summary and summary.value == todo_summary:
                    matching_todos.append(todo)
            except Exception:
                continue

        if not matching_todos:
            return f"No todo found with summary '{todo_summary}' in calendar '{calendar_name}'"

        if len(matching_todos) > 1:
            return f"Multiple todos found with summary '{todo_summary}'. Please be more specific."

        # Update the todo
        todo = matching_todos[0]
        vtodo = todo.vobject_instance.vtodo

        if new_summary:
            vtodo.summary.value = new_summary
        if new_description:
            if hasattr(vtodo, "description"):
                vtodo.description.value = new_description
            else:
                vtodo.add("description").value = new_description
        if new_due_date:
            due_dt = datetime.strptime(new_due_date, "%Y-%m-%d")
            if hasattr(vtodo, "due"):
                vtodo.due.value = due_dt
            else:
                vtodo.add("due").value = due_dt
        if new_priority:
            if hasattr(vtodo, "priority"):
                vtodo.priority.value = new_priority
            else:
                vtodo.add("priority").value = new_priority
        if new_status:
            vtodo.status.value = new_status.upper()
            if new_status.upper() == "COMPLETED":
                vtodo.add("completed").value = datetime.now()

        # Save the updated todo
        todo.save()

        return (
            f"Todo '{todo_summary}' updated successfully in calendar '{calendar_name}'"
        )
    except ValueError as e:
        return f"Error parsing date format: {str(e)}. Please use YYYY-MM-DD format."
    except Exception as e:
        return f"Error updating todo: {str(e)}"


@mcp.tool(name="delete_todo", description="Delete a todo from a calendar")
def delete_todo(
    calendar_name: str = Field(
        ..., description="Name of the calendar containing the todo"
    ),
    todo_summary: str = Field(..., description="Summary/title of the todo to delete"),
):
    """
    Tool to delete a todo from a specific calendar by its summary.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()
        calendar = next((cal for cal in calendars if cal.name == calendar_name), None)

        if not calendar:
            return f"Calendar '{calendar_name}' not found."

        todos = calendar.todos()
        matching_todos = []

        for todo in todos:
            try:
                vtodo = todo.vobject_instance.vtodo  # type: ignore
                summary = getattr(vtodo, "summary", None)
                if summary and summary.value == todo_summary:
                    matching_todos.append(todo)
            except Exception:
                continue

        if not matching_todos:
            return f"No todo found with summary '{todo_summary}' in calendar '{calendar_name}'"

        if len(matching_todos) > 1:
            return f"Multiple todos found with summary '{todo_summary}'. Please be more specific."

        # Delete the todo
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
    """
    Tool to mark a todo as completed.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()
        calendar = next((cal for cal in calendars if cal.name == calendar_name), None)

        if not calendar:
            return f"Calendar '{calendar_name}' not found."

        todos = calendar.todos()
        matching_todos = []

        for todo in todos:
            try:
                vtodo = todo.vobject_instance.vtodo  # type: ignore
                summary = getattr(vtodo, "summary", None)
                if summary and summary.value == todo_summary:
                    matching_todos.append(todo)
            except Exception:
                continue

        if not matching_todos:
            return f"No todo found with summary '{todo_summary}' in calendar '{calendar_name}'"

        if len(matching_todos) > 1:
            return f"Multiple todos found with summary '{todo_summary}'. Please be more specific."

        # Mark as completed
        todo = matching_todos[0]
        vtodo = todo.vobject_instance.vtodo

        vtodo.status.value = "COMPLETED"
        vtodo.add("completed").value = datetime.now()

        # Save the updated todo
        todo.save()

        return (
            f"Todo '{todo_summary}' marked as completed in calendar '{calendar_name}'"
        )
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
):
    """
    Tool to search for todos across all calendars.
    """
    try:
        principal = client.principal()
        calendars = principal.calendars()

        if not calendars:
            return "No calendars found."

        matching_todos = []

        for calendar in calendars:
            try:
                todos = calendar.todos()

                for todo in todos:
                    try:
                        vtodo = todo.vobject_instance.vtodo  # type: ignore
                        summary = getattr(vtodo, "summary", None)
                        description = getattr(vtodo, "description", None)
                        todo_status = getattr(vtodo, "status", None)
                        due = getattr(vtodo, "due", None)

                        summary_text = summary.value if summary else ""
                        description_text = description.value if description else ""
                        status_text = (
                            todo_status.value if todo_status else "NEEDS-ACTION"
                        )

                        # Filter by status if specified
                        if status and status_text.upper() != status.upper():
                            continue

                        if (
                            query.lower() in summary_text.lower()
                            or query.lower() in description_text.lower()
                        ):
                            status_indicator = (
                                "✓" if status_text == "COMPLETED" else "○"
                            )
                            matching_todos.append(
                                {
                                    "calendar": calendar.name,
                                    "summary": summary_text,
                                    "status": status_text,
                                    "due": (str(due.value) if due else "No due date"),
                                    "indicator": status_indicator,
                                    "description": (
                                        description_text[:100] + "..."
                                        if len(description_text) > 100
                                        else description_text
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
