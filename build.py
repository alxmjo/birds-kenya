#!/usr/bin/env python3
"""Build the Birds of Kenya Anki deck from birds.csv and the image cache.

    python3 build.py              # writes dist/Birds_of_Kenya.apkg and CREDITS.md

The build is offline: every image must already be in cache/images/.
To add birds, add rows to birds.csv and run fetch.py first.

The IDs below must never change. Anki matches notes on re-import by GUID
(derived from each bird's Wikidata QID) and by note type ID, so keeping them
fixed lets people update over an earlier version without losing progress.
"""
import argparse, copy, csv, json, os, shutil, sqlite3, sys, tempfile, zipfile
import genanki
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "birds.csv")
IMAGE_DIR = os.path.join(HERE, "cache", "images")
OUT = os.path.join(HERE, "dist", "Birds_of_Kenya.apkg")
CREDITS = os.path.join(HERE, "CREDITS.md")
LOOKALIKES_CSV = os.path.join(HERE, "lookalikes.csv")
PHOTOS_CSV = os.path.join(HERE, "photos.csv")
TEST_OUT = os.path.join(HERE, "dist", "Birds_of_Kenya_lookalikes_test.apkg")

MODEL_ID = 1760000000101   # note type "Bird (picture)"
DECK_ID = 1792585825895    # deck "Birds of Kenya"
PRESET_ID = 1760000000201  # deck options preset "Birds of Kenya"
LA_MODEL_ID = 1760000000102   # note type "Bird look-alikes"
LA_DECK_ID = 1760000000301    # deck "Birds of Kenya::Look-alikes"
LA_PRESET_ID = 1760000000202  # deck options preset "Birds of Kenya: look-alikes"
LA_SLOTS = 6  # most birds in one look-alike group; each slot is a card template

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

# Look-alike cards: one note per group of similar birds, one card per bird in the
# group, so siblings are buried and the group's birds come up on different days.
# Each bird has several photos (not the main deck's photo); a script shows one,
# chosen by the date, so the front and back match but the photo changes between reviews.
# Without the script, CSS shows the first photo only.
LA_CSS = CSS + """
.pics img:not(:first-child){display:none}
.choices{font-size:18px;color:#444;margin-top:10px}.nightMode .choices{color:#bbb}
.mark{font-size:15px;color:#666;text-align:left;border-top:1px dashed #ccc;margin-top:14px;padding-top:8px}
.nightMode .mark{color:#aaa}
.compare{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:12px}
.compare figure{margin:0;width:45%}.compare img{max-height:28vh}
.compare figcaption{font-size:13px;color:#666}.nightMode .compare figcaption{color:#aaa}"""

PICK_JS = """<script>(function(){var d=Math.floor((Date.now()-new Date().getTimezoneOffset()*6e4)/864e5);
document.querySelectorAll('.pics').forEach(function(el,j){var im=el.querySelectorAll('img');
var k=(d+j)%im.length;im.forEach(function(x,i){x.style.display=i==k?'inline':'none'})})})();</script>"""


def la_template(i):
    others = "".join(f'{{{{#Photos{j}}}}}<figure><div class="pics">{{{{Photos{j}}}}}</div>'
                     f'<figcaption>{{{{Name{j}}}}}</figcaption></figure>{{{{/Photos{j}}}}}'
                     for j in range(1, LA_SLOTS + 1) if j != i)
    return {
        "name": f"Look-alike → Name ({i})",
        "qfmt": f'{{{{#Photos{i}}}}}<div class="pics">{{{{Photos{i}}}}}</div>'
                f'<div class="choices">{{{{Choices}}}}</div>{PICK_JS}{{{{/Photos{i}}}}}',
        # Plain <hr>, not <hr id=answer>: Anki scrolls to #answer, which on these tall
        # backs would scroll the photo off the top of the screen.
        "afmt": (f'{{{{FrontSide}}}}<hr>{{{{Name{i}}}}}<br><i>{{{{Latin{i}}}}}</i>'
                 f'<div class="mark">{{{{Mark{i}}}}}</div><div class="compare">{others}</div>'
                 f'<div class="credits"><a href="https://www.wikidata.org/wiki/Special:GoToLinkedPage/enwiki/{{{{QID{i}}}}}">'
                 f'Wikipedia</a></div>{PICK_JS}'),
    }


LA_FIELDS = ["Group", "Choices"] + [f"{f}{i}" for i in range(1, LA_SLOTS + 1)
                                    for f in ("Name", "Latin", "QID", "Mark", "Photos")] + ["Credits"]
LA_MODEL = genanki.Model(
    LA_MODEL_ID,
    "Bird look-alikes",
    fields=[{"name": n} for n in LA_FIELDS],
    templates=[la_template(i) for i in range(1, LA_SLOTS + 1)],
    css=LA_CSS,
    sort_field_index=0,
)

# Anki's defaults, with new and review siblings buried.
PRESET_CHANGES = {"name": "Birds of Kenya", "new": {"perDay": 20, "bury": True},
                  "rev": {"perDay": 200, "bury": True}}
LA_PRESET_CHANGES = {"name": "Birds of Kenya: look-alikes", "new": {"perDay": 5, "bury": True},
                     "rev": {"perDay": 200, "bury": True}}

LICENCE_URLS = {"CC BY": "https://creativecommons.org/licenses/by/{v}",
                "CC BY-SA": "https://creativecommons.org/licenses/by-sa/{v}",
                "CC BY-NC": "https://creativecommons.org/licenses/by-nc/{v}"}


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


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_credits(rows):
    common = {r["qid"]: r for r in rows}
    rows = rows + [dict(common[p["qid"]], **{k: p[k] for k in ("commons_file", "photographer", "licence", "uploader")})
                   for p in read_csv(PHOTOS_CSV) if p["image"] and p["qid"] in common]
    lines = ["# Image credits", "",
             "Every photograph in this deck comes from Wikimedia Commons or iNaturalist and keeps its original licence. "
             "The images have been scaled to about 800 px wide and renamed. No other changes have been made.", "",
             "| Bird | Scientific name | Photographer | Licence | Source |", "|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["common"].lower()):
        who = r["photographer"]
        if who == "Unknown":
            who = "Not recorded on Commons" + (f" (uploaded by {r['uploader']})" if r.get("uploader") else "")
        if r["commons_file"].startswith("https://"):  # photo from outside Commons, e.g. iNaturalist
            page, site = r["commons_file"], "iNaturalist" if "inaturalist" in r["commons_file"] else "Source"
        else:
            page, site = "https://commons.wikimedia.org/wiki/File:" + quote(r["commons_file"].replace(" ", "_"), safe=","), "Commons"
        lines.append(f"| {r['common']} | *{r['latin']}* | {who.replace('|', chr(92) + '|')} | "
                     f"{licence_link(r['licence'])} | [{site}]({page}) |")
    with open(CREDITS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def add_preset(apkg, presets):
    """genanki can't store deck options, so insert the preset into the collection."""
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(apkg) as z:
        z.extractall(tmp)
        names = z.namelist()
    db = sqlite3.connect(os.path.join(tmp, "collection.anki2"))
    dconf_json, decks_json = db.execute("select dconf, decks from col").fetchone()
    dconf, decks = json.loads(dconf_json), json.loads(decks_json)
    for deck_id, preset_id, changes in presets:
        if str(deck_id) not in decks:
            continue
        preset = copy.deepcopy(dconf["1"])
        preset["id"] = preset_id
        for k, v in changes.items():
            if isinstance(v, dict):
                preset[k].update(v)
            else:
                preset[k] = v
        dconf[str(preset_id)] = preset
        decks[str(deck_id)]["conf"] = preset_id
    db.execute("update col set dconf=?, decks=?", (json.dumps(dconf), json.dumps(decks)))
    db.commit(); db.close()
    os.remove(apkg)
    with zipfile.ZipFile(apkg, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.write(os.path.join(tmp, n), n)
    shutil.rmtree(tmp)


def or_list(names):
    return names[0] + " or " + names[1] + "?" if len(names) == 2 else ", ".join(names[:-1]) + " or " + names[-1] + "?"


def lookalike_notes(birds):
    """One note per look-alike group, from lookalikes.csv and the extra photos in photos.csv."""
    by_qid = {r["qid"]: r for r in birds}
    photos = {}
    for p in read_csv(PHOTOS_CSV):
        if p["image"]:
            photos.setdefault(p["qid"], []).append(p)
    groups = {}
    for m in read_csv(LOOKALIKES_CSV):
        if m["active"].strip().lower() == "yes":
            groups.setdefault(m["group_id"], []).append(m)
    notes, media = [], []
    for gid, members in groups.items():
        slots = {int(m["slot"]): m for m in members}
        if len(slots) != len(members) or max(slots) > LA_SLOTS:
            sys.exit(f"Look-alike group {gid}: slots must be unique and at most {LA_SLOTS}")
        for m in members:
            if m["qid"] not in by_qid:
                sys.exit(f"Look-alike group {gid}: {m['qid']} is not an active bird in birds.csv")
            if not photos.get(m["qid"]):
                sys.exit(f"Look-alike group {gid}: no extra photos for {by_qid[m['qid']]['common']} (run fetch.py)")
        names = sorted(by_qid[m["qid"]]["common"] for m in members)
        values = {"Group": members[0]["group"], "Choices": or_list(names)}
        credits = []
        for i, m in slots.items():
            b, ps = by_qid[m["qid"]], photos[m["qid"]]
            values.update({f"Name{i}": b["common"], f"Latin{i}": b["latin"], f"QID{i}": b["qid"],
                           f"Mark{i}": m["field_mark"], f"Photos{i}": "".join(f'<img src="{p["image"]}">' for p in ps)})
            credits += [f"{b['common']}: {p['photographer']}, {p['licence']}" for p in ps]
            media += [os.path.join(IMAGE_DIR, p["image"]) for p in ps]
        values["Credits"] = "<br>".join(credits)
        notes.append(genanki.Note(model=LA_MODEL, fields=[values.get(f, "") for f in LA_FIELDS],
                                  guid=genanki.guid_for("lookalike", gid), tags=["lookalikes"]))
    return notes, media


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookalikes-only", action="store_true",
                    help="write only the look-alike subdeck, for testing")
    args = ap.parse_args()
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
    la_deck = genanki.Deck(LA_DECK_ID, "Birds of Kenya::Look-alikes", description=(
        "Tell similar birds apart. Best started once the main cards for these birds are familiar."))
    la_notes, la_media = lookalike_notes(rows)
    for n in la_notes:
        la_deck.add_note(n)

    out = TEST_OUT if args.lookalikes_only else OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if args.lookalikes_only:
        pkg = genanki.Package(la_deck)
        pkg.media_files = la_media
    else:
        pkg = genanki.Package([deck, la_deck])
        pkg.media_files = [os.path.join(IMAGE_DIR, r["image"]) for r in rows] + la_media
    pkg.write_to_file(out)
    add_preset(out, [(DECK_ID, PRESET_ID, PRESET_CHANGES), (LA_DECK_ID, LA_PRESET_ID, LA_PRESET_CHANGES)])
    if not args.lookalikes_only:
        write_credits(rows)
    print(f"Built {out}: {0 if args.lookalikes_only else len(rows)} birds, {len(la_notes)} look-alike groups")


if __name__ == "__main__":
    main()
