# Birds of Kenya — Anki deck

An [Anki](https://apps.ankiweb.net/) flashcard deck for learning to recognise 156 common birds of Kenya by sight.

Each card shows a photograph on the front. The back gives the common name, the scientific name and a link to the bird's Wikipedia article. Photo credits are listed in [CREDITS.md](CREDITS.md) rather than on the cards, to keep reviews uncluttered.

## Download

**[Download the latest version](https://github.com/alxmjo/birds-kenya/releases/latest)**: open the release and download `Birds_of_Kenya.apkg` under *Assets*.

## Import

- **Desktop (Windows, Mac, Linux):** File → Import, then choose the `.apkg` file.
- **AnkiMobile (iPhone/iPad):** open the `.apkg` file from the Files app or a download, and choose to open it in Anki.
- **AnkiDroid:** tap the `.apkg` file, or use ⋮ → Import in AnkiDroid.

On first import, tick **Import any deck presets** so the deck's settings come in too.

### Updating to a newer version

The deck's note and card IDs never change between versions. Import a new release over the old one and choose **Update notes: If newer**. Cards are updated in place, and your review history is kept.

## Contents

- 156 species, one card each (Picture → Name)
- A **Look-alikes** subdeck that trains telling similar birds apart: flamingos, collared doves, hornbills, starlings, sparrows, fiscals, robin-chats, sunbirds, weavers, raptors, vultures and lapwings. Each card shows a photo and the names of the birds in its group. The back gives the answer, a short field mark and photos of the other birds in the group. These cards use different photos from the main deck, and the photo changes from day to day. The subdeck has its own settings (5 new cards a day) and is best started once the main cards for those birds are familiar.
- Image filenames are hashed, so they don't give away the answer
- Every image comes from Wikimedia Commons, apart from one from iNaturalist; its author and licence are listed in [CREDITS.md](CREDITS.md), linked from the deck description in Anki

The species list is a hand-picked selection of birds that are widespread or often seen in Kenya. It is not a ranking based on sighting data.

## Licence and credits

The deck is released under [Creative Commons Attribution-ShareAlike 4.0](LICENSE) (CC BY-SA 4.0). This covers the card design and the arrangement of the content.

Each photograph keeps its own licence: CC0, CC BY, CC BY-SA, (in three cases) GFDL 1.2, or (in one case, the Grosbeak weaver) CC BY-NC 4.0. [CREDITS.md](CREDITS.md) lists the author, licence and source page for every image. The full GFDL 1.2 text is in [GFDL-1.2.txt](GFDL-1.2.txt).

Names and descriptions come from Wikipedia and Wikidata.

If you reuse or adapt this deck, keep the photo credits and share your version under CC BY-SA. The Grosbeak weaver photo is licensed for non-commercial use only, so remove or replace it before any commercial use.

## Building the deck

The deck is built from `birds.csv` (one row per bird, keyed by Wikidata ID) and the scaled photos in `cache/images/`.

```
pip install -r requirements.txt
python3 fetch.py   # only needed after adding rows: fetches photo, name and credits
python3 build.py   # writes dist/Birds_of_Kenya.apkg and regenerates CREDITS.md
```

To add a bird, add a row with its `qid` and `common` name, a `batch` tag such as `batch_002`, and `active` set to `yes`. Then run `fetch.py` and check `cache/contact_sheet.jpg` for unsuitable photos. To use a different photo, put its Commons file name in `commons_file`, clear `image`, and run `fetch.py` again. To retire a bird, set `active` to `no` instead of deleting the row.

### Look-alike cards

`lookalikes.csv` lists the groups: one row per bird, with a `group_id`, a `slot` (1–6, fixed for good, because it decides which card holds that bird's review history) and the field mark shown on the back. Each group becomes one note with one card per bird, so the birds in a group are buried from each other and come up on different days.

The look-alike photos are listed in `photos.csv` by Commons file name, usually three per bird, and never the photo the main deck uses. `fetch.py` downloads any row without an `image`. To find photos, list the birds in `candidates.txt` and run `candidates.py`. It draws numbered contact sheets in `cache/candidates/`; running it again for a bird shows only photos not offered before. If Wikimedia rate-limits your machine, push `candidates.txt` to a branch named `candidates/<anything>` and the *Find photo candidates* workflow runs it on GitHub. Check file names as well as thumbnails: Commons titles often reveal a captive bird, a specimen, or a photo taken outside the species' range.

`python3 build.py --lookalikes-only` writes `dist/Birds_of_Kenya_lookalikes_test.apkg` with only the Look-alikes subdeck, for testing.

If Wikimedia rate-limits your machine, push the new rows to a branch named `fetch/<anything>` instead. The *Fetch new birds* workflow then runs `fetch.py` on GitHub's servers and commits the photos and credits back to that branch.

Releases are published automatically. When `VERSION` changes on `main`, a GitHub Action builds the deck and publishes it as release `v<VERSION>`, using `RELEASE_NOTES.md` as the release text.

## Corrections

Spotted a misidentified bird or a wrong name? Please [open an issue](https://github.com/alxmjo/birds-kenya/issues).
