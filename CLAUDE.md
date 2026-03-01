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
│    ├─ Ninja API            │   ├─ Router    │
│    └─ OAuth setup          │   ├─ Skills    │
│                            │   └─ EventSub  │
│                                             │
│  db (Postgres :5432)     redis (:6379)      │
└─────────────────────────────────────────────┘
```

## Data Model

- **Bot** — A Twitch bot identity (e.g., Elsydeon, WorldFriendshipBot). Holds encrypted OAuth tokens.
- **Channel** — A channel where a bot is active. FK to Bot. Also stores the channel owner's OAuth tokens for moderation.
- **Command** — A text command (e.g., `!lurk`) defined per channel. Response text supports variables. `created_by` tracks who created it (Twitch username from `!addcom`, or channel owner name from imports).
- **Skill** — A Python-coded command toggled per channel. Logic lives in `bot/skills/` as handler classes, the model controls enable/disable and stores JSON config.
- **Counter** — A named counter per channel (e.g., death count, scare count). Dedicated model with `IntegerField` for atomic `F()` updates. Readable in command responses via `$(count.get name)`.
- **Alias** — A type-agnostic command alias per channel. Resolved early in the message pipeline to rewrite triggers before routing (e.g., `!ct` → `!count death`). Works for both text commands and skills.

## Commands vs Skills

**Commands** are text responses stored in the database. Anyone with mod/broadcaster permissions can create them via `!addcom`. They support variable substitution and `/me` action messages.

**Skills** are Python handler classes in `bot/skills/`. They handle behavior that text responses can't: counters, API calls, file reads, conditional logic, games. Each skill is a `SkillHandler` subclass registered in `SKILL_REGISTRY` and dispatched by the `CommandRouter`.

## Message Processing Pipeline

The `CommandRouter` (`bot/router.py`) is a TwitchIO Component with a single `event_message` listener. Processing order:

1. **Self-message guard** — Skip if chatter is the bot itself
2. **Prefix check** — Skip if message doesn't start with `!`
3. **Skip built-in commands** — Management commands handled by `ManagementCommands`
4. **Alias resolution** — Rewrite trigger via `Alias` model (e.g., `!ct` → `!count death`)
5. **Skill dispatch** — Look up handler in `SKILL_REGISTRY`, call `handler.handle()`
6. **Text command fallback** — Look up in `Command` table, process variables, respond

## Variable System

Variables use `$(namespace.property args)` syntax in command responses. Defined in `bot/variables.py` as a registry of handler classes. Each handler owns a namespace and has `resolve()` and `describe()` methods.

| Variable | Description |
|---|---|
| `$(user)` | Display name of the chatter who triggered the command |
| `$(target)` | First argument after the command (with `@` stripped). Falls back to `$(user)` if no argument given |
| `$(channel)` | Current channel name |
| `$(uses)` | How many times this text command has been used |
| `$(count.get <name>)` | Current value of a named counter |
| `$(count.label <name>)` | Display label of a named counter |
| `$(random.range N-M)` | Random integer between N and M |
| `$(random.pick a,b,c)` | Random choice from a comma-separated list |
| `$(query)` | Full argument string after the command name |
| `$(1)`, `$(2)`, ... | Positional arguments (1-based) |

### /me Action Messages

If a command's response starts with `/me `, the bot sends it as a Twitch action message (italicized). The optional `- ` separator after `/me` is also stripped (convention from Spoonee's commands).

### Security

- The bot ignores its own messages to prevent command chaining.
- `$(target)` strips leading `@` only. The self-message guard prevents injection of `!commands` or `/me` via target arguments.

## Alias System

Aliases are type-agnostic command rewrites. When someone types `!ct`, the router looks up the Alias table and rewrites it to `!count death` before routing. This works for both text commands and skills.

| Command | Permission | Description |
|---|---|---|
| `!alias <name> <target>` | Mod/Broadcaster | Create an alias (e.g., `!alias ct count death`) |
| `!unalias <name>` | Mod/Broadcaster | Remove an alias |
| `!aliases` | Everyone | List all aliases for the channel |

## Counter System

Counters are named per-channel values stored in the `Counter` model. They use Django `F()` expressions for atomic increments.

| Command | Permission | Description |
|---|---|---|
| `!count <name>` | Everyone | Show a counter's value |
| `!count <name> +` | Mod/Broadcaster | Increment a counter |
| `!count <name> -` | Mod/Broadcaster | Decrement a counter |
| `!count <name> set <N>` | Mod/Broadcaster | Set a counter to a specific value |
| `!counters` | Everyone | List all counters and their values |

Counters are also accessible in command responses via `$(count.get <name>)` and `$(count.label <name>)`. Counter values can be edited directly in Django admin.

## DeepBot Variable Mapping

For importing commands from DeepBot, these map to our system:

| DeepBot | Botbesties | Status |
|---|---|---|
| `@user@` | `$(user)` | Supported |
| `@target@` | `$(target)` | Supported |
| `@uptime@` | `$(uptime)` | Not yet implemented |
| `@game@` | `$(game)` | Not yet implemented |
| `@counter@`, `@getcounter@` | `$(count.get <name>)` | Supported (via Counter model) |
| `@customapi@` | — | Skill (not yet implemented) |
| `@readfile@` | — | Skill (not yet implemented) |
| `@if@` | — | Skill (not yet implemented) |
| `@followdate@`, `@hours@`, `@points@` | — | Skill (needs Twitch API) |

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
| `!alias <name> <target>` | Mod/Broadcaster | Create a command alias |
| `!unalias <name>` | Mod/Broadcaster | Remove a command alias |
| `!aliases` | Everyone | List all aliases |
| `!count <name> [+\|-\|set N]` | Mod/Broadcaster (mutations) | View or modify a counter |
| `!counters` | Everyone | List all counters |
| `!conch [question]` | Everyone | Magic Conch Shell (skill) |
| `!getyeflask` | Everyone | Random chance game (skill) |
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
