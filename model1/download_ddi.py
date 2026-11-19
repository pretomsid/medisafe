"""Download the DDInter 2.0 drug-drug interaction dataset (Model 1 training data).

    python download_ddi.py            # skips files that already exist
    python download_ddi.py --force    # download again

Source : https://ddinter2.scbdd.com/download/
Paper  : Tian et al., "DDInter 2.0", Nucleic Acids Research 2025, doi:10.1093/nar/gkae1004
License: CC BY-NC-SA 4.0 (non-commercial / academic use, attribution required)

Files are saved unchanged in data/ddinter/ together with SOURCE.json
(download date, sha256, row counts) so the exact training data can be traced.
Only the Python standard library is used.
"""
import argparse
import csv
import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://ddinter2.scbdd.com/static/media/download/ddinter_downloads_code_{}.csv"
CODES = "ABDHLPRV"  # ATC groups that DDInter publishes as separate files
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "data", "ddinter")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def summarize(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        levels, rows = {}, 0
        for r in reader:
            rows += 1
            lv = (r.get("Level") or "").strip() or "(blank)"
            levels[lv] = levels.get(lv, 0) + 1
        return reader.fieldnames, rows, levels


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="download even if the file exists")
    args = parser.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    files = []
    for code in CODES:
        url = BASE_URL.format(code)
        path = os.path.join(OUT_DIR, os.path.basename(url))
        if args.force or not os.path.exists(path):
            print(f"Downloading {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "medisafe-course-project"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(path + ".part", "wb") as out:
                out.write(resp.read())
            os.replace(path + ".part", path)
        else:
            print(f"Exists, skipped: {os.path.basename(path)}")
        columns, rows, levels = summarize(path)
        files.append({"atc_code": code, "file": os.path.basename(path), "url": url,
                      "sha256": sha256(path), "rows": rows, "columns": columns, "levels": levels})
        print(f"  {code}: {rows:,} rows  {levels}")

    meta = {
        "dataset": "DDInter 2.0",
        "page": "https://ddinter2.scbdd.com/download/",
        "citation": "Tian Y. et al. DDInter 2.0. Nucleic Acids Research 53(D1):D1356, 2025. doi:10.1093/nar/gkae1004",
        "license": "CC BY-NC-SA 4.0",
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    with open(os.path.join(OUT_DIR, "SOURCE.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"Saved {len(files)} files + SOURCE.json in {OUT_DIR}")


if __name__ == "__main__":
    main()
