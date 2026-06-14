"""Apply manual decisions to the 04z Fantrax crosswalk review.

Fills the review CSV `action` column (gsis_id or "new" per the 04z convention),
updates dim_fantrax_crosswalk (match_method='manual'), back-fills gsis_id into
fact_fantrax_adp, and leaves the filled review CSV in place as the decision
record. Collision-checks that no gsis_id ends up claimed by two scorer_ids.
"""
from datetime import date
from pathlib import Path

import pandas as pd

root = Path(r"C:\Users\benha\OneDrive\Documents\GitHub\Python-PowerBI-DynastyFantasyFootball")
REVIEW_CSV = root / "data" / "review" / "review_fantrax_crosswalk.csv"
XWALK = root / "data" / "dim_fantrax_crosswalk.parquet"
FACT = root / "data" / "fact_fantrax_adp.parquet"

# scorer_id -> gsis_id (or "new" = not in nflverse registry yet)
DECISIONS = {
    "06s66": "00-0040715",  # Cameron Skattebo -> Cam Skattebo RB NYG
    "060sy": "00-0037809",  # Chigoziem Okonkwo -> Chig Okonkwo TE WAS
    "06bg9": "00-0038685",  # Christopher Brooks -> Chris Brooks RB GB
    "050da": "00-0035357",  # Cameron Lewis -> Cam Lewis CB CHI
    "05yew": "00-0037034",  # DeAundre Alford -> Dee Alford CB BUF
    "06loy": "00-0039775",  # Eli Neal -> Elias Neal LB LAR
    "05jeg": "00-0036349",  # Kamren Curl -> Kam Curl SAF LAR
    "05jb2": "00-0036130",  # Justin Madubuike -> Nnamdi Madubuike DT BAL (name change)
    "04yqd": "00-0035253",  # Chauncey Gardner-Johnson -> C.J. Gardner-Johnson SAF BUF
    "06b7m": "00-0039176",  # Basil Chijioke Okoye -> Basil Okoye DT BAL
    "06b7i": "00-0039177",  # David Ebuka Agoha -> David Agoha DE TEN
    "06ao7": "00-0039149",  # Jartavius Martin -> Quan Martin SAF WAS
    "06sv7": "00-0040168",  # Quandarrius Robinson -> Que Robinson LB DEN
    "0617k": "00-0037587",  # Nathan Landman -> Nate Landman LB LAR
    "0617e": "00-0037585",  # Timothy Horne -> Timmy Horne DT TEN
    "072jx": "CAR787213",   # Robert Carter -> Rob Carter Jr. CB IND (2026)
    "07532": "RUB494866",   # Gabriel Rubio -> Gabe Rubio DE PIT (2026)
    "075cs": "ROB304777",   # Cameron Robertson -> Cam Robertson LB ARI (2026)
    "061c3": "00-0037633",  # Jake Hummel -> Jacob Hummel LB HOU
    "05rm2": "00-0036967",  # Joe Tryon -> Joe Tryon-Shoyinka LB PHI
    "04oio": "00-0034413",  # Foyesade Oluokun -> Foye Oluokun LB JAX
    "05rld": "00-0036940",  # Jayson Oweh -> Odafe Oweh LB WAS
    "060jy": "00-0037190",  # Ahmad Gardner -> Sauce Gardner CB IND
    "060x6": "00-0037041",  # Haggai Chisom Ndubuisi -> Haggai Ndubuisi DT TB
    "075hr": "THO086347",   # Christian Thomas -> Chris Thomas LB LV (2026)
    "0619e": "00-0037106",  # Jaylon Jones (CHI) — disambig collision w/ IND namesake
    # Not in nflverse registry yet (2026 UDFA camp bodies) — resolve on a
    # future dim_nfl_players refresh:
    "0755f": "new",         # Scooby Williams LB MIN
    "07696": "new",         # Jai'Onte' McMillan DB IND
    "07697": "new",         # Chase Wilson LB NYJ
    "076b3": "new",         # Zion Wilson DL PHI
    "075rf": "new",         # Tyce Westland DL DEN
    "075oz": "new",         # Jy Gilmore DB TB
    "075p0": "new",         # Riley Wilson LB TB
}

today = date.today().isoformat()

rev = pd.read_csv(REVIEW_CSV)
rev["action"] = rev["scorer_id"].map(DECISIONS).fillna("")
missing = rev[rev["action"] == ""]
if len(missing):
    raise SystemExit(f"unresolved review rows remain: {missing['player_name'].tolist()}")
# 0619e (Jaylon Jones CHI) was a silent disambig collision, not a review row.
rev.to_csv(REVIEW_CSV, index=False)

xw = pd.read_parquet(XWALK)
resolved = {k: v for k, v in DECISIONS.items() if v != "new"}
m = xw["scorer_id"].isin(resolved)
xw.loc[m, "gsis_id"] = xw.loc[m, "scorer_id"].map(resolved)
xw.loc[m, ["match_method", "match_score", "resolved_date"]] = ["manual", 100, today]
new_ids = [k for k, v in DECISIONS.items() if v == "new"]
xw.loc[xw["scorer_id"].isin(new_ids), ["match_method", "resolved_date"]] = ["new", today]

dups = xw[xw["gsis_id"].notna()].groupby("gsis_id")["scorer_id"].nunique()
dups = dups[dups > 1]
if len(dups):
    print(xw[xw["gsis_id"].isin(dups.index)][["scorer_id", "player_name", "gsis_id",
                                              "match_method"]].to_string(index=False))
    raise SystemExit(f"COLLISION: {len(dups)} gsis_id claimed by >1 scorer_id — not applied")
xw.to_parquet(XWALK, index=False)

fact = pd.read_parquet(FACT)
key = xw.set_index("scorer_id")["gsis_id"]
fact["gsis_id"] = fact["scorer_id"].map(key)
fact.to_parquet(FACT, index=False)

print(f"applied {len(resolved)} manual matches, {len(new_ids)} marked 'new'")
print(f"fact_fantrax_adp gsis coverage: {fact['gsis_id'].notna().sum()}/{len(fact)} "
      f"({fact['gsis_id'].notna().mean() * 100:.1f}%)")
print(xw["match_method"].value_counts().to_string())
