# Dynasty Fantasy Football

Data pipeline and owner tools for a 28-team, dual-conference IDP dynasty
fantasy football league. Python notebooks pull league data from Fantrax, NFL
data from nflverse and expert rankings from several sites into a star-schema
set of tables. Those tables feed a Power BI report, a Discord bot and a
trade-diagnostic web app.

## About the league

| Setting | Value |
|---|---|
| Format | Dynasty, IDP |
| Teams | 28 (14 per conference) |
| Conferences | Riddell (A01 to A14), Wilson (B01 to B14) |
| Salary cap | $300,000,000 per team |
| FA minimum | $2,000,000 |

League principles: owners come first, and every change is judged by what it
puts in an owner's hands. See
[PRINCIPLES.md](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/blob/main/docs/PRINCIPLES.md).

## What the project makes

- **Published tables.** One parquet file per table in `data/`. Power BI, the
  bot and the trade tool read these and nothing else.
- **Power BI report.** A semantic model and report in `pbi/mouserat2/`.
- **Discord bot.** Answers league questions from the published tables.
  Replies are private unless the person chooses to share.
- **Trade tool.** Positional surplus and need, mixed player and pick baskets,
  and live cap impact for a proposed trade. It lives at the
  [root of this site](../).

## In this site

- **Refresh schedule:** when each part of the data refreshes.
- **Running the pipeline:** how the scheduled run works and what stays manual.
- **Data sources:** every outside source, what it feeds and how often.
- **Data model:** every table and how the tables join.

The source code and the decision records are on
[GitHub](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball).
