# Official Bambu endpoints (L2 search + L0 metadata)

Both endpoints are undocumented but public (plain GET, no auth, no cookies) —
same `v1/*-service` microservice family. Reverse-engineering pattern published
by the **Bambuddy wiki** (`wiki.bambuddy.cool/features/makerworld/`, project
github.com/maziggy/bambuddy, upstream credit **Pr0zak/YASTL#51**); the Search
Service endpoint table is cross-referenced in
**[Doridian/OpenBambuAPI](https://github.com/Doridian/OpenBambuAPI)** `cloud-http.md`.

**2026-09-05 update — search endpoint found and verified.** The earlier
"search requires browser session state" hard conclusion (from Bambuddy wiki's
Limitations note) is now outdated for server-originated requests: the
`select/design2` endpoint returns full results from a plain server-side GET
with browser UA. This overturned the v2 architecture (DDG discovery) — DDG is
now fully removed.

## Search endpoint (L2 — discovery AND data in one call)

```
GET https://api.bambulab.com/v1/search-service/select/design2
    ?keyword=<query>&limit=<n>&offset=<n>&orderBy=<mode>
```

- No auth, no token. Browser UA + `Accept: application/json` → HTTP 200 JSON, ~0.6s.
- **Chinese keywords work natively** ("推牌" → 1706 matches, "手机支架" → 2855).
- Response: `{"total", "hits": [...], "suggest", "recommend", "insertion",
  "searchSessionId", "refreshId", "searchInstead", "keywordBlock", "blockedMessage", "token"}`.

### orderBy values (verified live 2026-09-05)

| value | behavior |
|---|---|
| (absent) / `score` | Bambu's own relevance ranking — best default |
| `hotScore` | trending |
| `downloadCount` | pure download count descending |
| `likeCount` | likes descending |
| `newUploads` | newest (dl=0 cold-start models on top — real data, not failures) |
| `boosts` | boost-token ranking |

Note: `orderBy` changes result count slightly (different total per mode —
filters applied differently); irrelevant for top-N use.

### Hit fields (useful subset)

| Field | Meaning |
|---|---|
| `id` `title` `slug` | design ID, **original-language title**, URL slug |
| `titleTranslated` | machine translation (usually EN) — **display fallback only** |
| `cover` `coverPortrait` `coverLandscape` | CDN cover images |
| `downloadCount` `likeCount` `collectionCount` `printCount` `commentCount` | real engagement numbers |
| `designCreator` | {uid, name, handle, avatar, …} |
| `isStaffPicked` `pickReason` | official staff-pick flag |
| `license` `isExclusive` `is_official` `is_printable` | licensing/flags |
| `tags` | plain strings (str/dict mixed types is a design-service quirk, not seen here — stay defensive) |
| `createTime` `hotScore` `designScore` | metadata |
| `designExtension.design_pictures[]` | full image gallery |

**Not in search hits:** `summary`/description text → fill via the design-service
endpoint (L0 second pass, ≤ limit calls). Do NOT copy `titleTranslated` over
`title` — it machine-translates Chinese models into English (「GAME BOY EDC 磁力推牌」
→ "GAME BOY EDC Magnetic Pusher").

### Related endpoints in the same family (probe-verified)

| Endpoint | Status | Notes |
|---|---|---|
| `/v1/search-service/select/all?keyword=` | 200 | aggregated design/design2d/user counts; `hits=null` without type param |
| `/v1/search-service/searchlist?keyword=` | 200 | hot-search words + curated lists (no design hits) |
| `/v1/search-service/suggest2?keyword=` | 200 | suggestion boxes (empty from server context) |
| `/v1/search-service/homepage/nav` | 200 | category nav keys (`Trending`, `category_400`…) |
| `/v1/search-service/select/design/nav?navKey=` | (per OpenBambuAPI) | category browse, Bearer in Handy traffic but plain GET works |

## Metadata endpoint (L0)

```
GET https://api.bambulab.com/v1/design-service/design/{design_id}
```

- No auth. ~10-120KB JSON, 65 fields. Returns `summaryTranslated` (zh) +
  `summary` (original), `coverUrl`, full `tags`, `categories`, plate info.
- **design object is at TOP LEVEL**, not under `.data` (`d["downloadCount"]` ✅).
- Same ID space as the search endpoint (both international). makerworld.com.cn
  IDs do NOT match — see below.

### Parsing pitfalls (bitten 2026-09-02, still valid)

1. **tags mixed types** — `['EDC', '玩具', {name: '推牌'}]`: iterate with isinstance
   checks or the whole result silently becomes None.
2. **Zero counts are REAL data** — cold-start models have `downloadCount: 0`.
   Display with `isinstance(n, int)`, never `n or '?'`.
3. **.cn site = separate ID space** (verified 2026-09-04): .cn numeric IDs hit
   the API return **completely unrelated models with no error** (silent
   mismatch — worse than failure). Only makerworld.com (any language prefix)
   IDs are valid. v3 sidesteps this by generating all URLs on makerworld.com.
4. **Throwaway creators** — `user_<digits>` names are not a credit signal.

## Compliance posture

- Single-search-per-keyword + ≤ limit metadata calls per query. No batch
  scraping, no auth bypass, no file downloads (downloads need login by design).
- Credit the chain when citing publicly: Bambuddy wiki / Pr0zak (YASTL#51) +
  Doridian/OpenBambuAPI for the Search Service endpoint table.

## Verified examples (2026-09-05)

- `keyword="phone stand"` → total 4652; top hit id 1976503 "THE BEST PHONE STAND"
  37,562 dl / 5,026 likes — matches the web UI's first results page.
- `keyword="推牌"` → total 1706; top hits are the real Chinese fidget-slider
  models (732713 "GAME BOY EDC 磁力推牌" 3,199 dl).
- `keyword="洞洞板 数据线 收纳"` → total 1473, SKÅDIS cable organizers on top.
- `keyword="asdfghjkl zxcv"` (nonsense) → no keywordBlock, loose matches return —
  relevance ranking keeps them sane; L3 gate still applies.