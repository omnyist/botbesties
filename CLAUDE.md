# Botbesties

Multi-tenant Twitch bot platform built with Django + TwitchIO 3.x.

## Architecture

Two Docker containers share the same codebase and PostgreSQL database:

- **server** — Daphne ASGI app serving Django admin, API, and OAuth setup pages on port 7177.
- **bot** — Runs `manage.py runbot`, which starts one `BotClient` (TwitchIO) per active bot record. Each bot gets its own AiohttpAdapter port (base 4343, incrementing).

```
┌─────────────────────────────────────────────┐
│  docker-compose                             │
│                                             │
│  server (Daphne :7177)   bot (runbot)       │
│    ├─ Django Admin         ├─ BotClient ×N  │
│    ├─ Ninja API            │   ├─ Components│
│    └─ OAuth setup          │   └─ EventSub  │
│                                             │
│  db (Postgres :5432)     redis (:6379)      │
└─────────────────────────────────────────────┘
```

## Data Model

- **Bot** — A Twitch bot identity (e.g., Elsydeon, WorldFriendshipBot). Holds encrypted OAuth tokens.
- **Channel** — A channel where a bot is active. FK to Bot. Also stores the channel owner's OAuth tokens for moderation.
- **Command** — A text command (e.g., `!lurk`) defined per channel. Response text supports variables. `created_by` tracks who created it (Twitch username from `!addcom`, or channel owner name from imports).
- **Skill** — A Python-coded command toggled per channel. Logic lives in `bot/components/`, the model controls enable/disable and stores JSON config.

## Commands vs Skills

**Commands** are text responses stored in the database. Anyone with mod/broadcaster permissions can create them via `!addcom`. They support variable substitution and `/me` action messages.

**Skills** are Python implementations in `bot/components/`. They handle behavior that text responses can't: counters, API calls, file reads, conditional logic, games. Each skill is a `commands.Component` subclass registered in `BotClient.setup_hook()`.

## Variable System

Variables use `$(name)` syntax in command responses. Defined in `bot/components/dynamic.py`:

| Variable | Description |
|---|---|
| `$(user)` | Twitch username of the person who triggered the command |
| `$(target)` | First argument after the command (with `@` stripped). Falls back to `$(user)` if no argument given |
| `$(channel)` | Current channel name |
| `$(count)` | How many times this command has been used |
| `$(random N-M)` | Random integer between N and M |
| `$(pick a,b,c)` | Random choice from a comma-separated list |

### /me Action Messages

If a command's response starts with `/me `, the bot sends it as a Twitch action message (italicized). The optional `- ` separator after `/me` is also stripped (convention from Spoonee's commands).

### Security

- The bot ignores its own messages to prevent command chaining.
- `$(target)` strips leading `@` only. The self-message guard prevents injection of `!commands` or `/me` via target arguments.

## DeepBot Variable Mapping

For importing commands from DeepBot, these map to our system:

| DeepBot | Botbesties | Status |
|---|---|---|
| `@user@` | `$(user)` | Supported |
| `@target@` | `$(target)` | Supported |
| `@uptime@` | `$(uptime)` | Not yet implemented |
| `@game@` | `$(game)` | Not yet implemented |
| `@counter@`, `@getcounter@` | — | Skill (not a text command) |
| `@customapi@` | — | Skill |
| `@readfile@` | — | Skill |
| `@if@` | — | Skill |
| `@followdate@`, `@hours@`, `@points@` | — | Skill (needs API) |

## Management Commands

| Command | Description |
|---|---|
| `manage.py runbot` | Start all active bot instances |
| `manage.py seed` | Create initial users, bots, and channels |
| `manage.py importcommands <json> --channel <name>` | Bulk import commands from JSON. Use `--dry-run` to preview. Sets `created_by` to channel owner name |

### Import JSON Format

```json
{
  "commands": [
    {"name": "lurk", "response": "/me - $(user) settles in for a cozy lurk.", "mod_only": false}
  ],
  "metadata": {
    "skipped_skills": ["caster", "checkme"]
  }
}
```

## Chat Commands

| Command | Permission | Description |
|---|---|---|
| `!addcom <name> <response>` | Mod/Broadcaster | Create a new text command |
| `!editcom <name> <response>` | Mod/Broadcaster | Edit an existing command's response |
| `!delcom <name>` | Mod/Broadcaster | Delete a command |
| `!commands` | Everyone | List all enabled commands |
| `!id` | Everyone | Show the bot's Twitch user ID |

## Deployment

Automated via GitHub Actions (`.github/workflows/deploy.yml`). Pushes to `main` trigger a deploy to the self-hosted runner on Saya.

- **Domain**: `bots.bardsaders.com` behind Cloudflare Zero Trust.
- **Server access**: `ssh saya`. Use `docker exec` for container interaction, not `docker compose`.
- **Startup sequence**: migrate → seed → collectstatic → Daphne.

### Static Files

WhiteNoise does not work under ASGI/Daphne (sync-only middleware). Static files are served via Django's `django.views.static.serve` through a URL route in `botbesties/urls.py`.

## Twitch IDs

| Name | Twitch User ID | Role |
|---|---|---|
| Avalonstar | 38981465 | Channel owner |
| Spoonee | 78238052 | Channel owner |
| Elsydeon | 66977097 | Bot |
| WorldFriendshipBot | 149214941 | Bot |

## Development

- **Python 3.13**, managed by `uv`.
- **Linting**: Ruff (config in `pyproject.toml`). Single-line imports, `from __future__ import annotations` required.
- **Database**: PostgreSQL 16. All models use UUID primary keys.
- **Encryption**: django-fernet-encrypted-fields for OAuth tokens.
