#!/usr/bin/env python3
"""Build the Birds of Kenya Anki deck from birds.csv and the image cache.

    python3 build.py              # writes dist/Birds_of_Kenya.apkg and CREDITS.md

The build is offline: every image must already be in cache/images/.
To add birds, add rows to birds.csv and run fetch.py first.

The IDs below must never change. Anki matches notes on re-import by GUID
(derived from each bird's Wikidata QID) and by note type ID, so keeping them
fixed lets people update over an earlier version without losing progress.
"""
import copy, csv, json, os, shutil, sqlite3, sys, tempfile, zipfile
import genanki
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "birds.csv")
IMAGE_DIR = os.path.join(HERE, "cache", "images")
OUT = os.path.join(HERE, "dist", "Birds_of_Kenya.apkg")
CREDITS = os.path.join(HERE, "CREDITS.md")

MODEL_ID = 1760000000101   # note type "Bird (picture)"
DECK_ID = 1792585825895    # deck "Birds of Kenya"
PRESET_ID = 1760000000201  # deck options preset "Birds of Kenya"

CSS = """.card{font-family:system-ui,-apple-system,sans-serif;font-size:22px;text-align:center;
color:#222;background:#fff}.card.nightMode{color:#eee;background:#1e1e1e}
img{max-width:100%;max-height:70vh}.credits{font-size:11px;color:#888;margin-top:14px}
.credits a{color:#0645ad;text-decoration:underline}
.nightMode .credits a{color:#7aa7ff}"""

MODEL = genanki.Model(
    MODEL_ID,
    "Bird (picture)",
    fields=[{"name": n} for n in ["Picture", "Common", "Latin", "Credits", "QID"]],
    templates=[{
        "name": "Picture → Name",
        "qfmt": "{{Picture}}",
        # Photo credits are kept in the Credits field and in CREDITS.md, but not shown during review.
        "afmt": ('{{FrontSide}}<hr id=answer>{{Common}}<br><i>{{Latin}}</i>'
                 '<div class="credits">'
                 '<a href="https://www.wikidata.org/wiki/Special:GoToLinkedPage/enwiki/{{QID}}">Wikipedia</a></div>'),
    }],
    css=CSS,
    sort_field_index=1,
)

# Anki's defaults, with new and review siblings buried.
PRESET_CHANGES = {"name": "Birds of Kenya", "new": {"perDay": 20, "bury": True},
                  "rev": {"perDay": 200, "bury": True}}

LICENCE_URLS = {"CC BY": "https://creativecommons.org/licenses/by/{v}",
                "CC BY-SA": "https://creativecommons.org/licenses/by-sa/{v}"}


def read_rows():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["active"].strip().lower() == "yes"]


def credit_line(r):
    return f"Photo: {r['photographer']}, {r['licence']}"


def licence_link(lic):
    if lic.startswith("GFDL"):
        return f"[{lic}](GFDL-1.2.txt)"
    kind, _, ver = lic.rpartition(" ")
    url = LICENCE_URLS.get(kind)
    return f"[{lic}]({url.format(v=ver)})" if url else lic


def write_credits(rows):
    lines = ["# Image credits", "",
             "Every photograph in this deck comes from Wikimedia Commons and keeps its original licence. "
             "The images have been scaled to about 800 px wide and renamed. No other changes have been made.", "",
             "| Bird | Scientific name | Photographer | Licence | Source |", "|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["common"].lower()):
        who = r["photographer"]
        if who == "Unknown":
            who = "Not recorded on Commons" + (f" (uploaded by {r['uploader']})" if r.get("uploader") else "")
        page = "https://commons.wikimedia.org/wiki/File:" + quote(r["commons_file"].replace(" ", "_"), safe=",")
        lines.append(f"| {r['common']} | *{r['latin']}* | {who.replace('|', chr(92) + '|')} | "
                     f"{licence_link(r['licence'])} | [Commons]({page}) |")
    with open(CREDITS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def add_preset(apkg):
    """genanki can't store deck options, so insert the preset into the collection."""
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(apkg) as z:
        z.extractall(tmp)
        names = z.namelist()
    db = sqlite3.connect(os.path.join(tmp, "collection.anki2"))
    dconf_json, decks_json = db.execute("select dconf, decks from col").fetchone()
    dconf, decks = json.loads(dconf_json), json.loads(decks_json)
    preset = copy.deepcopy(dconf["1"])
    preset["id"] = PRESET_ID
    for k, v in PRESET_CHANGES.items():
        if isinstance(v, dict):
            preset[k].update(v)
        else:
            preset[k] = v
    dconf[str(PRESET_ID)] = preset
    decks[str(DECK_ID)]["conf"] = PRESET_ID
    db.execute("update col set dconf=?, decks=?", (json.dumps(dconf), json.dumps(decks)))
    db.commit(); db.close()
    os.remove(apkg)
    with zipfile.ZipFile(apkg, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.write(os.path.join(tmp, n), n)
    shutil.rmtree(tmp)


def main():
    rows = read_rows()
    missing = [r["common"] for r in rows if not r["image"] or not os.path.exists(os.path.join(IMAGE_DIR, r["image"]))]
    if missing:
        sys.exit(f"Missing images (run fetch.py first): {', '.join(missing)}")
    if len({r["qid"] for r in rows}) != len(rows):
        sys.exit("Duplicate QIDs in birds.csv")

    deck = genanki.Deck(DECK_ID, "Birds of Kenya", description=(
        'Photo credits and licences: <a href="https://github.com/alxmjo/birds-kenya/blob/main/CREDITS.md">CREDITS.md</a>'))
    for r in rows:
        deck.add_note(genanki.Note(
            model=MODEL,
            fields=[f'<img src="{r["image"]}">', r["common"], r["latin"], credit_line(r), r["qid"]],
            guid=genanki.guid_for(r["qid"]),
            tags=[r["batch"]],
        ))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pkg = genanki.Package(deck)
    pkg.media_files = [os.path.join(IMAGE_DIR, r["image"]) for r in rows]
    pkg.write_to_file(OUT)
    add_preset(OUT)
    write_credits(rows)
    print(f"Built {OUT} with {len(rows)} birds")


if __name__ == "__main__":
    main()
