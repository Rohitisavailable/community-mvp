# Community Desk MVP

A local-first prototype for Admin login, project-scoped text knowledge, and a Hermes/Ollama answer path. It includes two seeded demo projects so you can verify that project data stays separate before adding real files. For a public prototype deployment, see [DEPLOYMENT.md](DEPLOYMENT.md).

## What is included

- One Admin account and a web dashboard (localhost in development; configurable for hosted deployment).
- Project A and Project B, each with its own SQLite database and full-text search index.
- `.txt` and `.md` uploads, stored and indexed only in the selected project's database.
- A project-aware chat. Retrieval always stays inside the selected project's database. Generation can use Backboard, the project Hermes profile, or Ollama; Backboard can also use its optional web-search fallback when project sources do not answer.
- Optional Backboard web search, enabled with `WEB_SEARCH_ENABLED=true`. The model is instructed to prefer project evidence and label web answers with direct URLs. Web search adds latency; check Backboard/provider billing before enabling it.
- Optional Telegram webhook integration: bind each group/private chat to one project, answer ordinary text messages or `/ask` questions with a typing indicator, and let configured admins add `.txt`/`.md` files or explicit HTTPS pages. Admins can also connect RSS/Atom feeds to Telegram channels; new feed entries are posted with optional keyword filters and duplicate protection.
- Discord application commands: bind a Discord server to one project with `/bind`, then allow any server member to ask that project's imported sources with `/ask`.
- Platform-neutral authenticated answer API at `POST /api/v1/ask` for adapters to connect other chat platforms to a project without exposing project data publicly.
- An MCP search tool with a fixed database path per Hermes profile. The default profile's example config is bound to Project A; the separate Project B profile config is bound to Project B.

Local development uses SQLite and your existing local Hermes/Ollama setup. Hosted mode uses Supabase Postgres for persistent project data and Waitress to serve the Flask app. The hosted prototype is Admin-only; it does not expose project answers to anonymous visitors.

## Start the dashboard on Windows

Open PowerShell in this directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

In `.env`, set a private local admin password, a random `APP_SECRET_KEY`, and an Ollama model tag that is already installed on your machine. For example:

```dotenv
ADMIN_EMAIL=admin@local.test
ADMIN_PASSWORD=choose-a-local-password
APP_SECRET_KEY=paste-a-long-random-value-here
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
HERMES_DEFAULT_API_KEY=
HERMES_DEFAULT_PORT=8642
COMMUNITY_PORT=8787
```

To use Backboard instead of the Hermes/Ollama path, set these values in `.env`:

```dotenv
AI_ENABLED=true
AI_PROVIDER=backboard
COMMUNITY_BACKBOARD_API_KEY=paste-your-server-side-key-here
BACKBOARD_LLM_PROVIDER=your-provider-name
BACKBOARD_MODEL_NAME=your-exact-model-id
WEB_SEARCH_ENABLED=true
```

Choose the provider and exact model ID from Backboard and check its pricing first. Both model settings are required to prevent accidentally using Backboard's API default. Set `WEB_SEARCH_ENABLED=true` to allow public web fallback when project evidence is missing or incomplete; Backboard's `Auto` mode decides when to search and adds latency. Keep this key in `.env` only for local development; `.env` is ignored by Git. Restart the app after changing environment values. On a successful answer the chat backend label should start with `Backboard (...)`; web answers must include URLs in the answer and appear as `Web:` sources.

Then start Ollama (if you want model-generated responses) and run:

```powershell
ollama list
ollama serve
```

If `ollama serve` says a server is already running, leave the existing Ollama process alone. In another PowerShell window:

```powershell
.\.venv\Scripts\python.exe .\app.py
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787). Sign in with the email/password from `.env`. The local fallback credentials are for localhost development only; set your own before sharing the app.

## Prove project separation

After signing in, ask **“What is this project's private test code?”** in both projects:

- Project A should reveal `ALPHA-QUARTZ-731` from `welcome.txt`.
- Project B should reveal `BRAVO-EMBER-942` from its own `welcome.txt`.

Also ask Project A for Project B's code (and vice versa). An answer must never contain the other project's private code; it may return only the selected project's matching excerpt or say it could not find an answer. The underlying stores are distinct files at `data/projects/project-a/knowledge.sqlite3` and `data/projects/project-b/knowledge.sqlite3`; retrieval receives the selected slug and opens only its database.

The seeded records are clearly fictional test data. Use the upload panel to add your own `.txt` or `.md` content after the boundary check.

## Connect your existing Hermes Telegram bot to Project A

Your existing Telegram gateway is on the Hermes `default` profile, so the provided `hermes/project-a-mcp.yaml` pins its read-only search tool to Project A's database. It contains workspace-specific absolute paths; if you move this folder, update those paths.

1. Confirm the dashboard is running at least once so both project databases have been created.
2. In PowerShell, run `hermes config edit` and merge the `project_knowledge` entry from `hermes/project-a-mcp.yaml` under the existing `mcp_servers:` mapping in `%LOCALAPPDATA%\hermes\config.yaml`. Keep one `mcp_servers:` key and preserve the rest of your existing settings. Do not replace the entire file with the snippet.
3. Add the contents of `hermes/project-agent-instructions.md` to the default profile's `SOUL.md` (or the profile's equivalent agent instructions). This tells the bot to call the project search tool, cite the filename, and decline answers not supported by Project A files.
4. Restart the Hermes gateway and send a question in the Telegram chat where your existing bot is enabled. Test with “What is Project A's private test code?”

The default profile's existing Telegram token/chat configuration is not copied or changed by this prototype. If the gateway reports an MCP spawn error, verify that `.venv` setup finished and the Python executable and project paths in the YAML still exist. Consult Hermes' [profiles documentation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/profiles.md) and [MCP documentation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/mcp.md) for the installed version's exact config layout.

## Run the Community Desk Telegram bot

For a webhook-backed Telegram bot that uses the hosted project's source store (rather than the local Hermes MCP profile), see [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md). It supports multiple project-bound chats, source upload/link commands, group-safe `/ask` messages, and RSS/Atom auto-posting to channels. A linked discussion group is required for channel-audience questions; channels themselves are broadcast-only in this MVP.

## Connect Discord or another chat platform

Follow [DISCORD_SETUP.md](DISCORD_SETUP.md) to add Community Desk slash commands to a Discord server. For a custom bot adapter on another platform, use the authenticated endpoint described in [PLATFORM_BOT_API.md](PLATFORM_BOT_API.md). Each integration is scoped to one project and must keep its API key server-side.

## Connect a separate Hermes profile to Project B

This configures a clean `community-project-b` profile with its own memory and sessions, local Ollama model, Project B-only MCP server/database, and a profile-authenticated route on the host gateway. In the current Hermes multiplexed setup, profiles share the default listener (usually `127.0.0.1:8642`); named profile API calls use `/p/community-project-b/v1/...`. The secondary profile stores its own `API_SERVER_KEY` but does not start a second listener. It does not copy or change the `default` profile and does not configure a Telegram token.

1. If you already have a model, check it with `ollama list`. If no model is installed, the script will ask for a model tag (default `qwen2.5:7b`) and tell you the `ollama pull` command to run before starting Hermes.
2. Make sure `.venv` is set up and start the dashboard once, so the Project B SQLite database exists.
3. In a PowerShell session where `hermes` works, change to this folder and run:

   ```powershell
   .\setup-project-b-hermes.ps1
   ```

   The script asks you to select an installed Ollama model or enter the tag you plan to install, then creates and configures the profile. It refuses to overwrite an existing `community-project-b` profile.
4. If you created the profile with an earlier version of this prototype setup script, run this one-time repair to remove its incorrect secondary API listener settings while preserving the model, Project B MCP mapping, and API key. It also copies that API key into the project's ignored `.env` so the dashboard can authenticate without exposing the Hermes profile folder to its process:

   ```powershell
   .\repair-project-b-hermes.ps1
   ```

   Then reload the Project B profile in the multiplexer:

   ```powershell
   hermes -p community-project-b gateway restart
   ```

   If Hermes says the profile is already served, that is expected; the restart reconnects that profile using its current config. Do not start a second gateway.

   Restart the dashboard process after the repair so it reads the API key and updated profile route. Stop its current PowerShell window with `Ctrl+C`, then run:

   ```powershell
   .\.venv\Scripts\python.exe .\app.py
   ```

5. Refresh the dashboard at `http://127.0.0.1:8787`, select Project B, and ask its seeded test-code question. The dashboard calls the Project B profile API; the profile's MCP server is separately pinned to Project B's SQLite database for agent/tool questions.

Hermes Agent currently requires an Ollama context length of at least 64,000 tokens for tool use. The profile requests `context_length: 64000`; Ollama itself may need `OLLAMA_CONTEXT_LENGTH=64000` set for its Windows service and restarted. Check the running value with `ollama ps`. This larger context can use more RAM/VRAM.

For a second Telegram bot, first create a different bot with BotFather and configure that token in the new profile. Do not run the existing token in both profiles. The script deliberately leaves Telegram disabled so it does not interfere with the current Project A bot.

## Local data and reset

All dashboard data is in this directory's `data/` folder by default. Set `COMMUNITY_DATA_DIR` in `.env` to move it elsewhere. Stop the dashboard before removing that folder to reset demo data, logins, and chats. Hermes profile data lives separately in Hermes' own home directory.

This remains a prototype with one Admin role, no account recovery, no audit controls, and no Founder/Team Member roles. The hosted setup is appropriate for a controlled public prototype, not a production multi-tenant service. See [DEPLOYMENT.md](DEPLOYMENT.md) for its operating limits and setup steps.
