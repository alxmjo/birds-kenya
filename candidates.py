#!/usr/bin/env python3
"""Find candidate Commons photos for birds and draw contact sheets to choose from.

List the birds in candidates.txt, one group per line:

    doves: Ring-necked dove, Red-eyed dove, Laughing dove

Names must match the `common` column of birds.csv. Then run

    python3 candidates.py

For each bird it collects up to 16 photos from the Commons category named after
the scientific name, plus a Commons search, skipping the photo the main deck
already uses and file names that suggest zoos, eggs, maps or specimens. It writes
cache/candidates/sheet_<group>.jpg (numbered thumbnails) and
cache/candidates/candidates.json (the file names behind the numbers). Chosen
files go into photos.csv; fetch.py then downloads them.

If Wikimedia rate-limits your machine, push candidates.txt to a branch named
candidates/<anything>: the *Find photo candidates* workflow runs this on
GitHub's servers and commits the sheets back to that branch.
"""
import hashlib, io, json, os, csv, time
import requests
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cache", "candidates")
API = "https://commons.wikimedia.org/w/api.php"
SKIP = ("zoo", "tierpark", "vogelpark", "walsrode", "captiv", "wüstenhaus", "aviary", "egg", "map", "range",
        "distribution", "juvenile", "juv", "skull", "museum", "specimen", "drawing", "illustration", "plate",
        "gould", "stamp", "nest")
S = requests.Session()
S.headers["User-Agent"] = "BirdsOfKenyaAnki/1.0 (https://github.com/alxmjo/birds-kenya)"


def get(url, **params):
    for i in range(10):
        r = S.get(url, params=params or None, timeout=60)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        time.sleep(max(int(r.headers.get("Retry-After", 0) or 0), 20 * (i + 1)))
    r.raise_for_status()


def candidates(latin, main_file, n=16):
    titles = []
    try:
        titles += [m["title"] for m in get(API, action="query", list="categorymembers", cmtitle="Category:" + latin,
                                           cmtype="file", cmlimit=50, format="json").json()["query"]["categorymembers"]]
    except Exception as e:
        print(f"  no category for {latin}: {e}")
    titles += [m["title"] for m in get(API, action="query", list="search", srnamespace=6, srlimit=40, format="json",
                                       srsearch=f'"{latin}" filetype:bitmap').json()["query"]["search"]
               if m["title"] not in titles]
    titles = [t for t in titles if t.lower().endswith((".jpg", ".jpeg"))
              and not any(s in t.lower() for s in SKIP) and t[5:] != main_file][:n]
    if not titles:
        return []
    pages = get(API, action="query", titles="|".join(titles), prop="imageinfo", iiprop="url", iiurlwidth=240,
                format="json").json()["query"]["pages"]
    items = sorted((p["title"][5:], p["imageinfo"][0]["thumburl"]) for p in pages.values() if "imageinfo" in p)
    out = []
    for name, url in items:
        try:
            out.append((name, Image.open(io.BytesIO(get(url).content)).convert("RGB")))
        except Exception as e:
            print(f"  skipped {name}: {e}")
        time.sleep(0.5)
    return out


def sheet(birds, path, w=200, h=175, cols=8):
    rows = sum(-(-len(items) // cols) for _, items in birds)
    img = Image.new("RGB", (cols * w, rows * h + 20 * len(birds)), "white")
    d = ImageDraw.Draw(img)
    y = 0
    for name, items in birds:
        d.text((5, y + 3), name, fill="blue")
        y += 20
        for i, (_, thumb) in enumerate(items):
            t = thumb.copy(); t.thumbnail((w - 8, h - 22))
            x, yy = (i % cols) * w, y + (i // cols) * h
            img.paste(t, (x + 4, yy + 2)); d.text((x + 4, yy + h - 18), str(i), fill="red")
        y += -(-len(items) // cols) * h
    img.save(path, quality=82)


def main():
    birds = {r["common"]: r for r in csv.DictReader(open(os.path.join(HERE, "birds.csv"), encoding="utf-8"))}
    os.makedirs(OUT, exist_ok=True)
    index = {}
    for line in open(os.path.join(HERE, "candidates.txt"), encoding="utf-8"):
        if ":" not in line or line.startswith("#"):
            continue
        group, names = line.split(":", 1)
        found = []
        for name in [n.strip() for n in names.split(",") if n.strip()]:
            b = birds[name]
            items = candidates(b["latin"], b["commons_file"].replace("_", " "))
            print(f"  {group.strip()}: {name}: {len(items)} candidates", flush=True)
            found.append((name, items))
            index[name] = {"qid": b["qid"], "files": [f for f, _ in items]}
        sheet(found, os.path.join(OUT, f"sheet_{group.strip()}.jpg"))
    with open(os.path.join(OUT, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
