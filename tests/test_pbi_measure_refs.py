import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "pbi/mouserat2/Mouserat2.SemanticModel/definition"
REPORT = ROOT / "pbi/mouserat2/Mouserat2.Report/definition"
MEASURES_TMDL = (MODEL / "tables/_Measures.tmdl").read_text(encoding="utf-8")
CULTURE = (MODEL / "cultures/en-US.tmdl").read_text(encoding="utf-8")

REMOVED_SOURCES = re.compile(r"keeptradecut|fantasypros|ktc_|fp_", re.I)


def measure_names() -> set:
    names = set()
    for m in re.finditer(r"^\tmeasure (?:'((?:[^']|'')+)'|(\S+))", MEASURES_TMDL, re.M):
        names.add((m.group(1) or m.group(2)).replace("''", "'"))
    return names


def report_measure_refs() -> dict:
    found = {}

    def add(name, path):
        found.setdefault(name, set()).add(str(path.relative_to(ROOT)))

    def walk(node, path):
        if isinstance(node, dict):
            measure = node.get("Measure")
            if isinstance(measure, dict):
                src = measure.get("Expression", {}).get("SourceRef", {})
                if src.get("Entity") == "_Measures" and "Property" in measure:
                    add(measure["Property"], path)
            for value in node.values():
                walk(value, path)
        elif isinstance(node, list):
            for value in node:
                walk(value, path)

    for f in sorted(REPORT.rglob("*.json")):
        walk(json.loads(f.read_text(encoding="utf-8")), f)
    return found


def test_measures_table_is_parsed():
    assert len(measure_names()) > 20


def test_every_report_measure_reference_resolves():
    names = measure_names()
    missing = {n: sorted(p) for n, p in report_measure_refs().items() if n not in names}
    assert not missing, missing


def test_culture_linguistic_metadata_is_valid_json():
    lines = CULTURE.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "linguisticMetadata =") + 1
    end = next(i for i, l in enumerate(lines) if l.strip() == "contentType: json")
    schema = json.loads("\n".join(l.rstrip("\r")[3:] for l in lines[start:end]))
    assert schema["Entities"]


def test_every_culture_measure_binding_resolves():
    names = measure_names()
    bound = set(re.findall(
        r'"ConceptualEntity": "_Measures",\s*"ConceptualProperty": "([^"]+)"', CULTURE))
    bound.discard("_Measures")
    assert bound
    assert not (bound - names), sorted(bound - names)


def test_every_dax_measure_reference_resolves():
    names = measure_names()
    body = re.sub(r"^\t+(?:formatString|displayFolder|lineageTag|annotation).*$", "",
                  MEASURES_TMDL, flags=re.M)
    body = re.sub(r"^\t///.*$", "", body, flags=re.M)
    used = set(re.findall(r"(?<![\w'\]])\[([^\]]+)\]", body))
    assert not (used - names), sorted(used - names)


def test_no_removed_source_is_named_in_the_power_bi_project():
    hits = []
    for f in (ROOT / "pbi/mouserat2").rglob("*"):
        if f.is_file() and f.suffix in {".tmdl", ".json"}:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if REMOVED_SOURCES.search(line):
                    hits.append(f"{f.relative_to(ROOT)}:{i}")
    assert not hits, hits[:20]
