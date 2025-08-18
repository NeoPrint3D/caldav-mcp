# CalDAV MCP Server

A Model Context Protocol (MCP) server that provides seamless integration with CalDAV calendars, enabling AI assistants to manage events and todos across your calendar systems.

## Features

- **Complete Calendar Management**: Create, read, update, and delete calendar events
- **Todo Management**: Full CRUD operations for todo items with status tracking
- **Batch Operations**: Create multiple events or todos efficiently
- **Search Capabilities**: Find events and todos across all calendars
- **Multi-Calendar Support**: Work with multiple calendars simultaneously
- **Timezone Handling**: Built-in Mountain Time to UTC conversion
- **Flexible Event Types**: Support for both timed and all-day events/todos

## Supported CalDAV Providers

This server works with any CalDAV-compliant service, including:
- **Nextcloud** (recommended)
- **Apple iCloud**
- **Google Calendar** (via CalDAV)
- **Yahoo Calendar**
- **Outlook.com**
- **FastMail**
- **SOGo**
- **Radicale**
- **Baikal**

## Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- CalDAV server credentials

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd caldav-mcp
```

### 2. Install Dependencies

Using uv (recommended):

```bash
uv sync
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```env
CALDAV_URL=https://your-caldav-server.com/remote.php/dav
CALDAV_USERNAME=your-username
CALDAV_PASSWORD=your-password
```

#### Common CalDAV URLs:

- **Nextcloud**: `https://your-domain.com/remote.php/dav`
- **iCloud**: `https://caldav.icloud.com`
- **Google**: `https://apidata.googleusercontent.com/caldav/v2/your-email@gmail.com/events`
- **Yahoo**: `https://caldav.calendar.yahoo.com`
- **Outlook**: `https://outlook.live.com/owa/calendar/00000000-0000-0000-0000-000000000000/`

### 4. Test the Installation

```bash
uv run main.py
```

The server should start and display available tools for calendar management.

## Setup Methods

### Method 1: Local Connection (Recommended for Development)

Run the MCP server locally and connect Claude Desktop directly.

#### 1. Start the Server

```bash
uv run main.py
```

#### 2. Configure Claude Desktop

Add to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "caldav": {
      "command": "uv",
      "args": ["run", "main.py"],
      "cwd": "/path/to/caldav-mcp"
    }
  }
}
```

### Method 2: Remote Connection (Recommended for Production)

For remote access, deploy the server on a VPS or home server and connect via HTTP. This method requires a secure network connection.

#### Network Security Solutions

Choose one of these VPN solutions for secure remote access:

##### Option A: Tailscale (Recommended)
Tailscale provides zero-config VPN with excellent security:

1. **Install Tailscale** on both server and client machines:
   ```bash
   # Ubuntu/Debian
   curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
   curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.list | sudo tee /etc/apt/sources.list.d/tailscale.list
   sudo apt update && sudo apt install tailscale
   
   # macOS
   brew install tailscale
   ```

2. **Authenticate both machines**:
   ```bash
   sudo tailscale up
   ```

3. **Get the Tailscale IP** of your server:
   ```bash
   tailscale ip -4
   ```

##### Option B: WireGuard
Self-hosted VPN solution:

1. **Install WireGuard** on server:
   ```bash
   sudo apt install wireguard
   ```

2. **Generate keys and configure** (see [WireGuard documentation](https://www.wireguard.com/quickstart/))

##### Option C: ZeroTier
Cloud-managed VPN:

1. **Create account** at [zerotier.com](https://zerotier.com)
2. **Install ZeroTier** on both machines
3. **Join the same network**

#### Remote Deployment

##### 1. Deploy the Server

```bash
# On your remote server
git clone <repository-url>
cd caldav-mcp
uv sync

# Create .env file with your CalDAV credentials
nano .env

# Run with custom host and port
uv run python main.py --host 0.0.0.0 --port 7030
```

##### 2. Using Docker (Alternative)

```bash
# Build the image
docker build -t caldav-mcp .

# Run the container
docker run -d \
  --name caldav-mcp \
  -p 7030:8000 \
  -e CALDAV_URL=your-caldav-url \
  -e CALDAV_USERNAME=your-username \
  -e CALDAV_PASSWORD=your-password \
  caldav-mcp
```

##### 3. Configure Claude Desktop for Remote Access

```json
{
  "mcpServers": {
    "caldav": {
      "command": "npx",
      "args": ["mcp-remote", "http://TAILSCALE-IP:7030/sse", "--allow-http"]
    }
  }
}
```

Replace `TAILSCALE-IP` with your server's Tailscale/VPN IP address.

## Usage Examples

Once connected, you can interact with your calendars using natural language:

### Event Management
- "Create a meeting tomorrow at 2 PM"
- "Show me my events for next week"
- "Update my dentist appointment to 3 PM"
- "Delete the cancelled project meeting"

### Todo Management
- "Add a todo to review the quarterly report"
- "Mark the budget planning task as completed"
- "Show me all pending todos"
- "Create a shopping list todo for this weekend"

### Batch Operations
- "Create calendar events for my entire conference schedule"
- "Add multiple todos for my project milestones"

## Time Zone Handling

The server includes built-in timezone conversion for Mountain Time:
- **Mountain Daylight Time (March-November)**: Adds 6 hours to convert to UTC
- **Mountain Standard Time (November-March)**: Adds 7 hours to convert to UTC

Military time is automatically converted to 24-hour format (e.g., `0645` becomes `06:45`).

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Verify CalDAV URL format
   - Check username/password credentials
   - Some providers require app-specific passwords

2. **Connection Timeouts**
   - Ensure firewall allows outbound HTTPS (port 443)
   - Check if your CalDAV server is accessible

3. **Remote Connection Issues**
   - Verify VPN connectivity between machines
   - Check that the server is listening on the correct IP/port
   - Ensure firewall allows the chosen port

### Debug Mode

Run with debug logging:

```bash
uv run python main.py --log-level debug
```

### Testing CalDAV Connection

```python
import caldav

client = caldav.DAVClient(
    url="YOUR_CALDAV_URL",
    username="YOUR_USERNAME", 
    password="YOUR_PASSWORD"
)

try:
    principal = client.principal()
    calendars = principal.calendars()
    print(f"Found {len(calendars)} calendars")
    for cal in calendars:
        print(f"- {cal.name}")
except Exception as e:
    print(f"Connection failed: {e}")
```

## Security Considerations

- **Use HTTPS**: Always use HTTPS CalDAV URLs in production
- **VPN Required**: Never expose the MCP server directly to the internet
- **App Passwords**: Use app-specific passwords when available
- **Environment Variables**: Keep credentials in `.env` files, never commit them
- **Firewall**: Restrict access to necessary ports only

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request
