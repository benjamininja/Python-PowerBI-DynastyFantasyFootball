# League Discord Bot

A discord.py command bot that fetches dynasty data from this GitHub repo and
posts formatted rankings in the league server. Authored from the
`discord-bot-github-fetch` skill — that skill is the source of truth for
architecture, security gates, and Railway deploy.

## Command (v1)

`/rankings` (also `!rankings`) — a **format-scoped, per-position board**.

| Arg | Default | Notes |
|---|---|---|
| `fmt` | `SF` | League format: `SF`, `TEPP` (offense), or `IDP` (defense). |
| `position` | all | Filter to one position (e.g. `QB`, `LB`). |
| `source` | best for format | `KTC` for SF/TEPP, `FantasyPros` for IDP. |
| `limit` | `10` | Players per position (max 25). |

Why format-scoped: no single format+source spans all positions — SF/TEPP hold
offense, IDP holds defense (FantasyPros only). One board = one format.

## Configuration

Copy `.env.example` → `.env` and fill in real values (`.env` is gitignored).

| Var | Purpose |
|---|---|
| `DISCORD_BOT_TOKEN` | Bot token (Developer Portal → Bot → Reset Token) |
| `DISCORD_GUILD_ID` | League server id (Developer Mode → right-click server → Copy ID) |
| `GITHUB_PAT` | Fine-grained PAT, Contents read-only, this repo |
| `GITHUB_OWNER` / `GITHUB_REPO` / `GITHUB_REF` | Repo + branch to read (defaults baked in) |
| `DISCORD_COMMAND_PREFIX` | Prefix-command prefix, default `!` |

**Discord portal:** enable the **Message Content** privileged intent
(Bot → Privileged Gateway Intents) or `!`-prefix commands silently do nothing.
Slash commands work without it.

## Run locally

```bash
cd discord_bot
pip install -r requirements.txt
python bot.py
```

The bot logs in over the gateway and stays running. Slash commands sync to your
guild on startup (instant).

## Deploy (Railway)

Persistent worker, deployed from this GitHub repo. See the skill's
`references/railway-deploy.md` for full steps. Summary:

1. Create a Railway service from the connected repo.
2. Set `rootDirectory` = `discord_bot`.
3. Set the env vars above as **service variables** (never commit them).
4. Start command and restart policy come from `railway.json` (`python bot.py`,
   `ON_FAILURE` capped at 5 retries so a bad token/config can't crash-loop).
5. No HTTP port / domain needed — it's a gateway worker.
6. Verify the deployment reaches **SUCCESS** and the bot shows online.

## Layout

```
config.py         # env → Config; fails loud on missing required vars
github_fetch.py   # GitHub contents API → DataFrame, TTL cache
rankings.py       # the rankings command (Cog) + embed rendering
bot.py            # entrypoint: intents, hybrid commands, guild sync, gateway
railway.json      # start command + bounded restart policy (deploy contract)
```

## Extend

Add a command as its own `@commands.hybrid_command` (own module or this Cog),
keep all data access in `github_fetch.py`, map columns via the skill's
`references/data-model.md`, and respect Discord embed limits. The startup sync
surfaces new commands immediately.
