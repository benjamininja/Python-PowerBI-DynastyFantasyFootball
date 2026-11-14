# How this project uses other sites' data

Last updated: 2026-11-12

Material changes are noted here, at the top. Every change to this page goes
through a pull request.

## 1. Who we are

This page is signed by [SIGNATURE], co-commissioner of the "Dead Money"
Fantasy Football league. The league is one private league of 28 teams. This
project, Mouserat, is its data pipeline, report, Discord bot and trade tool.

Members pay dues. Prizes come from the dues, and a small share covers the
project's running costs. The project sells nothing, shows no ads and makes
no profit.

## 2. Why we publish

Owners come first in this project ([docs/PRINCIPLES.md](PRINCIPLES.md)).
We publish the league's data so every member can see how their league is
run. That is the whole purpose.

## 3. How we read: five promises

1. Our scheduled readers send an identifying User-Agent that links to this
   page.
2. We honour robots.txt: the `User-agent: *` group, and any lines that name
   our agent.
3. We run at most one scheduled run a day per source. For Fantrax, we stay
   within the login limits we have set ourselves.
4. A 403 is never retried. A 429 makes us back off.
5. We check each site's terms before we build a reader for it, and again
   each season.

## 4. What we publish and what we never publish

**Published:**
- the league's own data;
- numbers we compute ourselves;
- a source's data, only where its terms allow it, with credit.

**Never published:**
- owners' personal details;
- money amounts;
- raw captures of other sites' pages;
- source data that its terms do not allow us to publish.

## 5. Credit

Every place that shows a source's data credits that source by name and
link.

Credit that a source's licence requires on this page itself:

- **nflverse** data is used under CC BY 4.0. Credit nflverse as the data
  source: <https://nflverse.com>.

## 6. Takedowns

If a site asks us to stop, then within 72 hours:

- the reader stops;
- that source's rows leave the next published snapshot;
- the source's terms record in [SOURCES.md](SOURCES.md) notes the request.

On request, we also scrub the source's files from the repository's history.

## 7. About AI

The scheduled readers are ordinary scripts. They send their own User-Agent.
AI agents (Claude) help write the code and run one-off checks. Those checks
stop at any robots.txt line that names them.

## 8. Contact

Write to [CONTACT ADDRESS], a mailbox kept only for data-use questions and
takedown requests.

## 9. Each source in detail

[SOURCES.md](SOURCES.md) lists every source: what we read, how often, under
which terms, and any permission we have asked for or been given.
