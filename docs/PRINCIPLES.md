# League principles

Built by millennial excellence; you're welcome. Principles below.

They bind every owner, the commissioner included.

1. **We ask why before what.** Every rule, every ruling and every build
   states its reason before the decision. "Because I said so" is not a reason.
2. **Nothing great happens without individual effort.** The league gives
   every owner the same information. What you do with it is your work, and it
   decides your season. The tools inform; they never decide for you.
3. **Stay vigilant; humans gonna habitual line step.** Every rule will be
   tested at its edge: by owners, by the commissioner, and by the people and
   agents who build the tools. So rules have hard edges and are enforced by
   machine, not by memory or good faith.
4. **Trust is optional, evidence is mandatory.** Every number the league
   shows traces to a record you can check yourself. A dispute is settled by
   the record, not by anyone's word.
5. **Soft-hand libertarianism where applicable.** Few rules, enforced
   exactly. Inside them the choices are yours: no vetoes on trade value, no
   lineup policing, no approved strategy. The league's job is to capture the
   data and serve it to you. It does not apply to collusion or to owner
   privacy.

## For builders, human and agent

Owners are front and center. Judge every change by what it puts in an
owner's hands.

| # | Where the repo already does it | A violation looks like |
|---|---|---|
| 1 | ADRs, grilling tickets, the plan gate | A design change merged with no recorded why |
| 2 | The bot, trade-bud and the published snapshot give information; nothing decides for an owner | A feature that issues a verdict or acts on an owner's behalf |
| 3 | Required CI checks, `pii-scan`, deny rules, Gate checks, cap math computed once | A rule kept only by a reminder; a rule broken once with no check added |
| 4 | Public repo and snapshot, the ledger as provenance, the source manifest, "done" shown by command output | A number with no traceable source; "done" with no output |
| 5 | Data capture and publishing; owner PII confined to one private table | A tool that blocks a legal move; owner PII or team names in a public file |
