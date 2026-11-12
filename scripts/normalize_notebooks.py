import json
import sys
from pathlib import Path


def split_lines(text):
    lines = text.split("\n")
    return [l + "\n" for l in lines[:-1]] + ([lines[-1]] if lines[-1] else [])


def normalize_notebook(nb):
    for cell in nb.get("cells", []):
        src = cell.get("source", "")
        if not isinstance(src, str):
            src = "".join(src)
        cell["source"] = split_lines(src)
    return nb


def render(nb):
    return json.dumps(nb, ensure_ascii=False, indent=1) + "\n"


def normalize_file(path):
    path = Path(path)
    old = path.read_bytes().decode("utf-8")
    new = render(normalize_notebook(json.loads(old)))
    if new == old.replace("\r\n", "\n"):
        return False
    path.write_bytes(new.encode("utf-8"))
    return True


def main(argv):
    changed = [p for p in argv if normalize_file(p)]
    for p in changed:
        print(f"normalized {p}")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
