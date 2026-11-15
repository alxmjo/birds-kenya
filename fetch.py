#!/usr/bin/env python3
"""Fill in new rows of birds.csv from Wikipedia, Wikidata and Wikimedia Commons.

Add a row with just `qid` and `common` (plus `batch`, `active` = yes), then run:

    python3 fetch.py

For each row without an image it fetches:
  - the lead image of the English Wikipedia article (scaled to 800 px wide),
  - the scientific name from Wikidata (P225), if `latin` is empty,
  - photographer, licence and file name from Commons.
It then writes cache/contact_sheet.jpg so the new photos can be checked by eye
(reject maps, eggs, illustrations and wrong subjects). Existing rows are untouched.
"""
import argparse, csv, hashlib, io, os, re, sys, time
import requests
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "BirdsOfKenyaAnki/1.0 (https://github.com/alxmjo/birds-kenya)"}
WIDTH = 800
S = requests.Session()
S.headers.update(UA)


def get(url, **params):
    for i in range(10):
        r = S.get(url, params=params or None, timeout=60)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        time.sleep(int(r.headers.get("Retry-After", 0) or 0) or 5 * (i + 1))
    r.raise_for_status()


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def fetch(row):
    qid = row["qid"].strip()
    ent = get("https://www.wikidata.org/w/api.php", action="wbgetentities", ids=qid,
              props="sitelinks|claims", sitefilter="enwiki", format="json").json()["entities"][qid]
    title = ent["sitelinks"]["enwiki"]["title"]
    if not row.get("latin"):
        row["latin"] = ent["claims"]["P225"][0]["mainsnak"]["datavalue"]["value"]
    pages = get("https://en.wikipedia.org/w/api.php", action="query", prop="pageimages", piprop="name",
                titles=title, redirects=1, format="json", formatversion=2).json()["query"]["pages"]
    fname = pages[0].get("pageimage")
    if not fname:
        raise RuntimeError(f"no lead image on Wikipedia page '{title}'")
    info = get("https://commons.wikimedia.org/w/api.php", action="query", titles="File:" + fname,
               prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=WIDTH,
               format="json", formatversion=2).json()["query"]["pages"][0]["imageinfo"][0]
    meta = info["extmetadata"]
    img = Image.open(io.BytesIO(get(info["thumburl"]).content)).convert("RGB")
    if img.width > WIDTH:
        img = img.resize((WIDTH, round(img.height * WIDTH / img.width)), Image.LANCZOS)
    name = "bird_" + hashlib.sha1(qid.encode()).hexdigest()[:10] + ".jpg"
    img.save(os.path.join(HERE, "cache", "images", name), quality=85)
    row.update(image=name, commons_file=fname.replace("_", " "),
               photographer=strip_html(meta.get("Artist", {}).get("value")) or "Unknown",
               licence=strip_html(meta.get("LicenseShortName", {}).get("value")))
    if not row["licence"].startswith(("CC BY", "CC0", "Public domain", "GFDL")):
        print(f"  check licence for {row['common']}: {row['licence']}")
    return img


def contact_sheet(items, path):
    w, h = 260, 220
    cols = 5
    sheet = Image.new("RGB", (cols * w, -(-len(items) // cols) * h), "white")
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    for i, (label, img) in enumerate(items):
        t = img.copy(); t.thumbnail((w - 10, h - 30))
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(t, (x + 5, y + 5)); d.text((x + 5, y + h - 22), label, fill="black")
    sheet.save(path, quality=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(HERE, "birds.csv"))
    args = ap.parse_args()
    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    new = [r for r in rows if r["active"].strip().lower() == "yes" and not r.get("image")]
    if not new:
        print("Nothing to fetch.")
        return
    os.makedirs(os.path.join(HERE, "cache", "images"), exist_ok=True)
    fetched, failed = [], []
    for r in new:
        try:
            fetched.append((r["common"], fetch(r)))
            print(f"  {r['common']}: {r['commons_file']} ({r['licence']})")
        except Exception as e:
            failed.append(r["common"]); print(f"  FAILED {r['common']}: {e}")
        time.sleep(1)
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    if fetched:
        contact_sheet(fetched, os.path.join(HERE, "cache", "contact_sheet.jpg"))
        print("Check cache/contact_sheet.jpg before building.")
    if failed:
        sys.exit(f"{len(failed)} failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
