import os

def parse_document(text):
    header, _, body = text.partition("\n\n")
    meta = {}
    for line in header.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()
    meta["content"] = body.strip()
    meta.setdefault("sensitivity", "restricted")
    return meta

with open("docs/08_team_credentials.txt") as f:
    result = parse_document(f.read())

for key, value in result.items():
    print(f"{key}: {value[:60]}")