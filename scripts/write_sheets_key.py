"""Write the Sheets service-account key file from the environment (#643, #614).

Reads GOOGLE_SHEETS_KEY_JSON, strips a leading byte-order mark and surrounding
whitespace, checks it is a JSON object with the type, client_email and
private_key fields, and writes it back with json.dump to the path in argv[1]
(default: GOOGLE_SHEETS_KEY_FILE). On failure it prints one line naming the
check that failed and exits 1. No branch prints, formats or raises any part
of the value: messages are fixed text plus, for bad JSON, the line, column
and character position the parser reports.
"""
from __future__ import annotations

import json
import os
import sys

SECRET_ENV = "GOOGLE_SHEETS_KEY_JSON"
PATH_ENV = "GOOGLE_SHEETS_KEY_FILE"
REQUIRED_FIELDS = ("type", "client_email", "private_key")
BOM = "﻿"


class KeyCheckError(Exception):
    pass


def clean_key(raw: str | None) -> dict:
    if raw is None or not raw.strip(BOM + " \t\r\n"):
        raise KeyCheckError(f"{SECRET_ENV} is empty")
    text = raw.strip()
    text = text.lstrip(BOM).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise KeyCheckError(
            f"{SECRET_ENV} is not JSON (line {int(e.lineno)}, column {int(e.colno)}, "
            f"char {int(e.pos)})") from None
    if not isinstance(data, dict):
        raise KeyCheckError(f"{SECRET_ENV} is JSON but not an object")
    for field in REQUIRED_FIELDS:
        v = data.get(field)
        if not isinstance(v, str) or not v.strip():
            raise KeyCheckError(f"{SECRET_ENV} has no {field} field")
    if data["type"] != "service_account":
        raise KeyCheckError(f"{SECRET_ENV} type field is not service_account")
    return data


def write_key(data: dict, path: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else os.environ.get(PATH_ENV, "")
    if not path:
        print(f"Sheets key: no output path (argument or {PATH_ENV}).")
        return 1
    try:
        data = clean_key(os.environ.get(SECRET_ENV))
    except KeyCheckError as e:
        print(f"Sheets key: {e}.")
        return 1
    try:
        write_key(data, path)
    except OSError:
        print("Sheets key: the key file could not be written.")
        return 1
    print("Sheets key: written.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
