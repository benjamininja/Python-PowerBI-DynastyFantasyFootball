# Fantrax authed login from a GitHub Actions runner: the spike

Part of #225 (child of map #70, "In-season Fantrax league flows"). It makes
the spike of #92 ready for the owner to fire. ADR-0015 hosts the ETL on
Actions **gated on this spike**. An agent does not store the secrets, fire
the workflow or log in to Fantrax; those are the owner's.

## Gist

- One workflow, `.github/workflows/fantrax-runner-spike.yml`, fired by hand
  from `main`. It installs the authed path on `ubuntu-latest`, logs in once
  headless, makes the four reads #92 lists, and reports only verdicts, HTTP
  statuses and seconds.
- **Before the TOTP login code lands, a run cannot get past the code
  prompt.** `FantraxScraper._login` in `04a` fills the email and password
  and never answers a second-factor prompt, and `pyotp` is not in
  `requirements.txt`. The spike reports that stop as `needs_code`. It still
  answers whether the runner is challenged on the way to the prompt. The
  login-code change is parked (no ticket yet); the driver needs no change
  when it lands, because it calls `_login` as it stands.

## What the authed path needs on a runner

Read from `04a`, `04s`, `04t`, `04v` and `04w`; nothing was run.

| Need | Where it comes from | On a runner |
|---|---|---|
| A real browser | `04a` launches a Playwright persistent Chromium context, `headless=True` | `python -m playwright install --with-deps chromium` (no display or Xvfb needed) |
| Python packages | importing `04a` imports `etl_helpers` (pandas, pyarrow, requests, thefuzz) and reads `dim_position` from the checkout | `pip install -r requirements.txt`, the same file `tests.yml` installs |
| Credentials | `_creds()` reads `FANTRAX_EMAIL` and `FANTRAX_PASSWORD` from the environment; `python-dotenv` is optional | environment secrets, passed to one step only |
| A session | the profile dir `data/.pw_profile` holds the cookies | a runner starts empty, so every run is a full login; the driver uses a throwaway temp dir |
| A second factor | owner's decision on #92 (2026-09-27): TOTP, `FANTRAX_TOTP_SECRET` | **not in the login code yet** (see Gist) |
| Writable disk | `_login` saves `login_debug.png` into `raw_dir` when the form fails | the driver points `raw_dir` at a temp dir; nothing is uploaded |

The four reads reuse the payload builders of the notebooks that make them,
with one row asked for each:

| Read | Built from | Note |
|---|---|---|
| `getPlayerStats` | `FantraxScraper._player_stats_payload` (`04a`) | one row, offense group |
| `getLiveScoringStats` | `period_requests` and `payload` (`04s`) | period 1 |
| `getTeamRosterInfo` | `payload` (`04s`), `{teamId, period}` | **rebuilt from the schema note** in `inseason-schema-extraction.md`; `04s` dropped this call (#118) and no notebook holds its request. A `page_error` that is not a permission code points at this request's shape before it points at the account. The team id is the first `fantrax_team_id` of `dim_fantasy_teams`, public identity, never printed |
| `getTransactionDetailsHistory` | `txn_payload` (`04t`) | one row, view `CLAIM_DROP` |

`getPlayerStats` goes first: it is the probe that tells a live session from a
dead one. The other three run only if the probe says the session is live.

## Set up once (owner)

1. Repository Settings, Environments, New environment, name
   `fantrax-spike`.
2. In the environment, Deployment branches and tags, Selected branches and
   tags, add the rule `main`. This is what keeps any other branch from
   reading the secrets. The workflow also carries
   `if: github.ref == 'refs/heads/main'`.
3. Under Environment secrets add these three, by name:
   - `FANTRAX_EMAIL`
   - `FANTRAX_PASSWORD`
   - `FANTRAX_TOTP_SECRET` (the bare base32 setup key, as in `.env.example`)

Which account the three secrets hold is the owner's choice. Question 2 of
#92 asks about an account without commissioner rights, and only that
account's run answers it; each account that is tried needs its own
authenticator key. The workflow reads whatever the secrets hold.

## Fire

Actions tab, workflow `fantrax-runner-spike`, Run workflow, branch `main`.
Or, from a terminal at the repo root:

```
gh workflow run fantrax-runner-spike.yml --ref main
```

It has no schedule and no other trigger. The environment may ask for a
reviewer's approval if one is configured; approve it.

## Read the output

Open the run, then the job's summary page; the same table is in the log of
the last step. The repository is public, so both are public: nothing in
them but what is listed below.

**Login line** (one of):

| Outcome | Meaning | Next |
|---|---|---|
| `passed` | the probe read came back authed | read the table |
| `challenged` | Cloudflare answered the page or a read with its challenge header, or showed its interstitial. The run stops | question 1 of #92 is answered: see the fallback below |
| `needs_code` | the login form took the email and password and the next screen asked for the authenticator code. Not a block | run again once the TOTP login code has landed |
| `failed` | no challenge and no code prompt, and the probe was not authed. Wrong password, a changed login form, or a timeout | the line under the headline names the exception class, never its message |

**Read table**, one row per read: HTTP status, a verdict, a code and the
seconds.

| Verdict | Meaning |
|---|---|
| `ok` | HTTP 2xx, a JSON body, no `pageError` |
| `page_error` | HTTP 200 with a Fantrax `pageError`; the `Code` column holds its code when it looks like one (`A-Z`, `0-9`, `_`), else `other`. This is how a refused read shows |
| `not_logged_in` | `WARNING_NOT_LOGGED_IN` |
| `cf_challenge` | Cloudflare's challenge header on the reply |
| `http_error`, `bad_body`, `no_response` | a non-2xx status, a body that is not JSON, or no reply at all (the exception class is shown) |
| `skipped` | no request was made (no team id in `dim_fantasy_teams`) |

**Step table**: the two installs (timed by the workflow) and the driver's
own total. The login and each read carry their seconds in the lines above.
The run page shows the job's total and every step's time as well.

A green job means the spike produced an answer, not that the login passed:
read the headline. Only a missing secret or a driver failure turns the job
red.

## Record the three answers on #92

Comment on #92 with the block below, filled from the run. Names of teams
and accounts stay out of it.

```
Spike run: <date>, workflow run <number>, runner ubuntu-latest.
1. Login from a runner: <passed | challenged | needs_code | failed>. Runs so far: <n> on <n> different days, <n> passed, <n> challenged.
2. Account without commissioner rights: <used | not used>. Reads: getPlayerStats <verdict>, getLiveScoringStats <verdict>, getTeamRosterInfo <verdict>, getTransactionDetailsHistory <verdict>.
3. Runtime: install python packages <s>, install chromium <s>, login <s>, reads <s> in all, job total <m s>.
```

Question 1 asks for several runs on different days: fire it again on each.
A run measures a cold install (no pip cache), the slowest case; the daily
workflow will cache.

The comment on #92 of 2026-09-27 also asks how long a session lasts. This
spike cannot measure that: a runner starts with an empty profile, so every
run is a fresh login. It needs a persisted profile, which is a design for
#93.

## If the runner is challenged

ADR-0015 and #92 already say what follows; the spike does not try anything
else:

- **No CAPTCHA workaround of any kind.** The driver changes no browser
  fingerprint, header or timing to avoid a challenge, and none is to be
  added.
- The fallback is a residential host: the authed captures (`04a`, `04s`,
  `04t`, `04v`, `04w`) stay on the home-PC task, and everything else runs on
  Actions.
- Report it on #92 as answer 1 and stop firing.

## What the driver does not do

- It refuses to start off Actions (`GITHUB_ACTIONS` must be `true`).
- It prints no payload, cookie, header value, page text, exception message,
  team id or account detail, and uploads nothing: no artifact, screenshot or
  trace.
- It makes no write call to Fantrax and writes no data file.
- It does not retry a login or a read.

## Parked

The TOTP step in `_login` and the dependency on `pyotp`: any change the
login code itself needs to run headless. The workflow already passes
`FANTRAX_TOTP_SECRET` to the driver's step so it needs no edit then.
