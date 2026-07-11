# League Discord Bot

A discord.py command bot that fetches dynasty data from this GitHub repo and
posts formatted rankings in the league server. Authored from the
`discord-bot-github-fetch` skill — that skill is the source of truth for
architecture, security gates, and Railway deploy.

## Commands

All commands are **hybrid** (slash `/cmd` + prefix `!cmd`) and **private by
default** — the result goes only to you (slash → ephemeral with a "Post
publicly" button; prefix in a public channel → DM). Pass `share: true` to post
publicly in one step.

### `/rankings` — format-scoped, per-position dynasty board

| Arg | Default | Notes |
|---|---|---|
| `fmt` | `SF` | League format: `SF`, `TEPP` (offense), or `IDP` (defense). |
| `position` | all | Filter to one position (e.g. `QB`, `LB`). |
| `source` | best for format | `KTC` for SF/TEPP, `FantasyPros` for IDP. |
| `limit` | `10` | Players per position (max 25). |

Why format-scoped: no single format+source spans all positions — SF/TEPP hold
offense, IDP holds defense (FantasyPros only). One board = one format.

### `/adp` — Fantrax ADP board (with league-ownership overlay)

One overall board sorted by ADP ascending; two lines per player so ADP, salary,
overall rank, position/team/age, and the player's owner in *our* league all fit.

| Arg | Default | Notes |
|---|---|---|
| `position` | all | Filter to one position group. |
| `limit` | `15` | Players to show (max 50). |

The owner column is blank for anyone not yet drafted and fills in as teams draft.

### `/player <name>` — single-player card

Resolves a name (normalize + substring; asks you to disambiguate a collision
like the two Josh Allens), then shows dynasty ranks + value per source (for the
player's format — IDP for defense, SF otherwise), composite + Fantrax ADP, and
the player's contract in our league if rostered.

### `/cap` — league salary-cap standings

Every team's spend and remaining cap, grouped by conference (division names from
`dim_division`), sorted by current spend.

### `/roster <team>` — a team's roster + contracts

Resolve a team by abbreviation or name; players listed by cap hit with contract
and status. A team that hasn't drafted yet gets a friendly note with its
available cap instead of an empty board.

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
github_fetch.py   # GitHub contents API → DataFrame, TTL cache (all data access)
delivery.py       # privacy routing + ShareView + respond_with_embeds wrapper
render.py         # embed pagination + null-safe cell formatting (shared)
rankings.py       # /rankings cog + query
adp.py            # /adp cog + query
player.py         # /player cog + query
cap.py            # /cap cog + query
roster.py         # /roster cog + query
bot.py            # entrypoint: intents, cog registration, guild sync, gateway
railway.json      # start command + bounded restart policy (deploy contract)
tests/offline_smoke.py  # no-network harness: build every command, assert limits
```

## Test (offline, no Discord/network)

```bash
.botvenv/Scripts/python.exe tests/offline_smoke.py
```

Monkeypatches `fetch_parquet` to read the local `data/` parquet, builds every
command's embeds, and asserts Discord's limits — also catches schema drift.

## Extend

Add a command as its own module with a `@commands.hybrid_command` cog. Keep data
access in `github_fetch.py`, build `(name, value)` fields and call
`render.paginate_fields`, then `delivery.respond_with_embeds` (which gives you
defer, off-loop fetch, error handling, and the private-by-default routing for
free). Map columns via the skill's `references/data-model.md`. Register the cog's
`setup_*` in `bot.py`; the startup sync surfaces the command immediately.
