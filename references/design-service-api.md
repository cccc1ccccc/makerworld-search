# Official Bambu design-service API (L0 data layer)

Discovered 2026-09-02 during skill debugging. This endpoint **overturned the session's
earlier "real counts unobtainable" conclusion** — before concluding a data source is
unreachable, check this endpoint first.

## Endpoint

```
GET https://api.bambulab.com/v1/design-service/design/{design_id}
```

- No auth, no token, no cookies. Plain GET with browser UA → HTTP 200, ~10-120KB JSON.
- design_id = the numeric ID in any makerworld.com(.cn) model URL
  (`/en/models/717070-phone-stand` → `717070`). The same ID serves all language variants
  (`/en/`, `/ru/`, `/zh/` paths are the same model).

## Provenance & compliance

- Undocumented public endpoint. Reverse-engineered pattern published by the **Bambuddy
  wiki** (`wiki.bambuddy.cool/features/makerworld/`, project github.com/maziggy/bambuddy),
  upstream credit **Pr0zak/YASTL#51**.
- Bambuddy uses it for public metadata reads (`makerworld:view` scope); downloads require
  MakerWorld login, metadata does not.
- Usage posture: single-call-per-design enrichment, no batch scraping, no auth bypass.
  When citing publicly (小红书 posts / calls for an official API), credit the chain above.

## Returns (65 fields; useful subset)

| Field | Meaning |
|---|---|
| `downloadCount` `likeCount` `collectionCount` `printCount` `commentCount` `readCount` | real engagement numbers |
| `coverUrl` | CDN cover image (makerworld.bblmw.com / public-cdn.bblmw.com) |
| `title` / `titleTranslated` | original + translation (prefer translated) |
| `summary` / `summaryTranslated` | HTML description → strip tags before display |
| `tags` | **mixed: plain strings AND {name:...} dicts in one array** |
| `categories` | list of {id, name, slug, ...} dicts |
| `designCreator` | {uid, name, avatar, fanCount...}; name may be `user_<digits>` throwaway |
| `isStaffPicked` | official staff-pick flag (boolean) |
| `license` `isPrintable` `allowReCreation` `createTime` `updateTime` `instances[]` | licensing & plate info |

## Parsing pitfalls (all bitten 2026-09-02)

1. **tags mixed types** — `['EDC', '玩具', {name: '推牌'}]`: iterate with isinstance checks;
   calling `.get("name")` on a str element raises AttributeError inside the try block,
   which silently converts the WHOLE result to None.
2. **Zero counts are REAL data** — `downloadCount: 0` means a cold-start model, not a
   fetch failure. Display logic must use `isinstance(n, int)`, never `n or '?'`
   (falsy-0 renders as '?', hiding real information).
3. **Language variants share one design_id** — `/en/models/2696620` and
   `/ru/models/2696620` are the same model. Dedup by design_id (prefer .cn/zh URL as
   canonical, keep others as alt_urls) or every hot model appears 2-3×.
4. **Throwaway creators** — `designCreator.name = user_1051639588` is a numeric throwaway
   account; apply the same non-credit rule as DDG-title author signals.

## Verified examples (2026-09-02)

- design 717070 "Phone Stand" (SabreDesign): **21,192 downloads / 6,178 likes**
- design 735370 "Dishwasher status slider, magnetic": 130 dl / 49 likes / 152 collects
- design 2696620 "磁铁推牌 / Magnetic Push Slider": **0 downloads** (cold start — the
  DDG text-heuristic had wrongly ranked it #1 via a leaked "4.5k" page count; official
  data corrected the ranking)

## What it does NOT provide

- **No search/list endpoint** — you still need discovery (DDG `site:` or a user-provided
  URL) to obtain design_ids. This is precisely the gap to call on Bambu to open:
  the official forum thread #205669 ("Feature Request: MakerWorld API or RSS Feed")
  shows the community has requested API access with no official plans announced.
  Argument for the call-to-action: metadata reads already work (this endpoint proves it);
  only search + official documentation + MCP wrapper are missing.
- **No 3MF download** — file downloads need login; give users the link to download
  themselves.