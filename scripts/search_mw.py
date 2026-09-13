#!/usr/bin/env python3
"""
makerworld-search — v3 pipeline: official search-service API + design-service enrichment.

Usage:
  python3 search_mw.py "phone stand" [--source auto|cn|intl|printables] [--limit 6] [--order score]
  python3 search_mw.py --meta "https://makerworld.com/en/models/717070-phone-stand"

Architecture (v3): keyword search hits Bambu's official search-service
(`GET /v1/search-service/select/design2`) — no token, real relevance ranking by
Bambu's own algorithm, every hit already carries real download/like/collection
counts, cover, tags, staff-pick flag. The design-service metadata endpoint
(`GET /v1/design-service/design/{id}`) is kept as a light second pass to add
summary text (search hits carry no description) + translated title.

v3 removed the DDG discovery layer entirely — the official search API makes it
obsolete: better relevance, zero rate-limits-against-us, no Cloudflare wall,
and it works for Chinese keywords natively.

Output: JSON to stdout (agent consumes and renders L3 cards).
"""

import argparse
import html as _html
import json
import re
import sys
import time
from urllib.parse import urlparse

import requests

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Official (undocumented but public) Bambu endpoints — same `v1/*-service`
# microservice family. Reverse-engineering pattern documented by the Bambuddy
# wiki (upstream credit: Pr0zak/YASTL#51); endpoint list cross-referenced with
# Doridian/OpenBambuAPI cloud-http.md (Search Service table).
SEARCH_API = "https://api.bambulab.com/v1/search-service/select/design2"
DESIGN_API = "https://api.bambulab.com/v1/design-service/design/{design_id}"

# orderBy values verified live (2026-09-05): score (default relevance),
# hotScore, downloadCount, likeCount, newUploads, boosts.
ORDER_BY = {
    "score": None,        # API default — Bambu's own relevance ranking
    "hot": "hotScore",
    "downloads": "downloadCount",
    "likes": "likeCount",
    "new": "newUploads",
    "boosts": "boosts",
}


def _strip(s) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(s))
    return _html.unescape(re.sub(r"\s+", " ", s)).strip()


# ---------------------------------------------------------------------------
# L2/L0 fused layer: official search — discovery AND real data in one call
# ---------------------------------------------------------------------------

def _official_search(keyword: str, limit: int = 6, order: str = "score", timeout: int = 15) -> dict:
    """Query Bambu's official search-service. No token, no login.

    Every hit already carries real engagement numbers + cover + tags +
    staff-pick, ranked by Bambu's own relevance algorithm.
    Returns a dict: {"total", "hits": [normalized row], "error": str}
    """
    params = {"keyword": keyword, "limit": limit, "offset": 0}
    ob = ORDER_BY.get(order)
    if ob:
        params["orderBy"] = ob
    out = {"total": 0, "hits": [], "error": ""}
    try:
        r = requests.get(SEARCH_API, params=params, headers=UA, timeout=timeout)
        if r.status_code != 200:
            out["error"] = f"HTTP {r.status_code}"
            return out
        d = r.json()
        if not isinstance(d, dict):
            out["error"] = "non-dict response"
            return out
        out["total"] = d.get("total") or 0
        for h in d.get("hits") or []:
            creator = h.get("designCreator") or {}
            # tags arrive as plain strings from search (unlike design-service's
            # mixed str/dict arrays — but stay defensive: same upstream family)
            tags = []
            for t in h.get("tags") or []:
                if isinstance(t, dict):
                    tags.append(t.get("name") or "")
                elif isinstance(t, str):
                    tags.append(t)
            out["hits"].append(
                {
                    "url": f"https://makerworld.com/en/models/{h.get('id')}-{h.get('slug') or ''}",
                    # title = original-language title from official search;
                    # titleTranslated only fills in when original is empty.
                    # titleTranslated is a machine translation into English —
                    # prefer the original (「GAME BOY EDC 磁力推牌」, not
                    # "GAME BOY EDC Magnetic Pusher").
                    "title": h.get("title") or h.get("titleTranslated") or "",
                    "title_translated": h.get("titleTranslated") or "",
                    "source": "official_search",
                    "desc": "",
                    "downloads": h.get("downloadCount"),
                    "likes": h.get("likeCount"),
                    "collections": h.get("collectionCount"),
                    "prints": h.get("printCount"),
                    "comments": h.get("commentCount"),
                    "staff_pick": bool(h.get("isStaffPicked")),
                    "cover": h.get("cover") or "",
                    "author": creator.get("name") or "",
                    "author_handle": creator.get("handle") or "",
                    "tags": [t for t in tags if t][:8],
                    "license": h.get("license") or "",
                    "create_time": h.get("createTime") or "",
                    "official": True,
                }
            )
        if d.get("keywordBlock"):
            out["error"] = f"keyword blocked: {d.get('blockedMessage') or 'no message'}"
        if not out["hits"] and not out["error"]:
            sug = d.get("suggest") or {}
            opts = sug.get("options") if isinstance(sug, dict) else None
            if opts:
                out["error"] = f"no hits; suggestions: {', '.join(map(str, opts[:5]))}"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:80]}"
    return out


# ---------------------------------------------------------------------------
# L0 second pass: design-service metadata (summary + translated title)
# ---------------------------------------------------------------------------

def _official_meta(design_id, timeout: int = 15) -> dict | None:
    """Fetch official public metadata for one design. No token needed.

    Search hits carry counts/cover/tags already; this adds the summary text
    (search API returns no description) and zh-translated title.
    """
    try:
        r = requests.get(DESIGN_API.format(design_id=design_id), headers=UA, timeout=timeout)
        if r.status_code != 200:
            return None
        d = r.json()
        if not isinstance(d, dict) or "id" not in d:
            return None
        creator = d.get("designCreator") or {}
        tags = []
        for t in d.get("tags") or []:
            if isinstance(t, dict):
                tags.append(t.get("name") or t.get("nameTranslated") or "")
            elif isinstance(t, str):
                tags.append(t)
        return {
            "id": d.get("id"),
            "title": d.get("titleTranslated") or d.get("title") or "",
            # summaryTranslated is a machine translation (zh for EN models).
            # Unlike the title case (where the original is kept and
            # titleTranslated only FALLS BACK), summaries deliberately prefer
            # the translated field: the primary audience reads zh and a rough
            # zh summary beats an EN one for gatekeeping. Keep this asymmetry
            # in mind if the audience changes — title policy must NOT follow
            # this (original titles are user-facing identity).
            "summary": _strip(d.get("summaryTranslated") or d.get("summary"))[:240],
            "downloads": d.get("downloadCount"),
            "likes": d.get("likeCount"),
            "collections": d.get("collectionCount"),
            "staff_pick": bool(d.get("isStaffPicked")),
            "cover": d.get("coverUrl") or "",
            "tags": [t for t in tags if t][:8],
            "author": creator.get("name") or creator.get("nickName") or "",
            "license": d.get("license") or "",
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Complement layer: Printables public GraphQL API (kept from v2 — official
# search covers MakerWorld only; Printables stays a cross-site complement)
# ---------------------------------------------------------------------------

def _printables_api_impl(query: str, limit: int) -> list:
    endpoint = "https://api.printables.com/graphql/"
    payload = {
        "query": """
        query printList($first: Int, $after: Cursor, $sort: PrintSort, $category: String, $name: String) {
          print(sort: $sort, after: $after, first: $first, category: $category, name: $name) {
            edges {
              node {
                id
                name
                slug
                likesCountAllTime
                downloadsCountAllTime
                images {
                  filePath
                }
              }
            }
          }
        }
        """,
        "variables": {"first": limit, "name": query, "sort": "POPULARITY_ALL_TIME"},
    }
    try:
        r = requests.post(endpoint, json=payload, headers=UA, timeout=8)
        if r.status_code != 200:
            return []
        edges = r.json().get("data", {}).get("print", {}).get("edges", [])
        out = []
        for e in edges:
            n = e.get("node", {})
            imgs = n.get("images") or []
            img = ""
            if imgs and imgs[0].get("filePath"):
                img = "https://media.printables.com/" + imgs[0]["filePath"]
            out.append(
                {
                    "url": f"https://www.printables.com/model/{n.get('id')}/{n.get('slug') or ''}",
                    "title": n.get("name") or "",
                    "source": "printables.com",
                    "desc": "",
                    "downloads": n.get("downloadsCountAllTime"),
                    "likes": n.get("likesCountAllTime"),
                    "image": img,
                }
            )
        return out[:limit]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# --meta mode: metadata for one known model URL (kept from v2, now goes
# straight to the official design-service endpoint instead of og: scraping)
# ---------------------------------------------------------------------------

def _meta_single(url: str) -> dict:
    out = {"url": url, "fetched": False}
    m = re.search(r"makerworld\.com(?:\.cn)?/(?:[a-z-]+/)?models/(\d+)", url)
    if not m:
        out["error"] = "not a makerworld model URL"
        return out
    domain = urlparse(url).netloc
    if domain.endswith(".cn"):
        out["error"] = (
            "makerworld.com.cn uses a separate ID space — IDs do not match the "
            "design-service API (verified 2026-09-04); use the makerworld.com mirror"
        )
        return out
    meta = _official_meta(m.group(1), timeout=15)
    if meta:
        out.update(meta)
        out["fetched"] = True
    else:
        out["error"] = "design-service API returned no data"
    return out


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def _quality_signal(r: dict) -> tuple:
    """Heuristic quality signals for rows without official counts (Printables).

    Official-search rows already rank by Bambu's own algorithm; these signals
    only fill gaps and act as a minor tie-breaker (5x weight).
    """
    title = (r.get("title") or "").lower()
    desc = (r.get("desc") or "").lower()
    text = title + " " + desc
    score = 0
    signals = []
    for kw, w in [("no support", 2), ("无支撑", 2), ("ams", 1), ("multicolor", 1),
                  ("多色", 1), ("parametric", 2), ("参数化", 2), ("customizer", 2),
                  ("test print", 2), ("实测", 2), ("已优化", 2), ("optimized", 2)]:
        if kw in text:
            score += w
            signals.append(kw)
    return score, signals


def _rank_key(r: dict) -> int:
    # official counts first; fall back to top-level counts (Printables rows)
    dl = r["downloads"] if isinstance(r.get("downloads"), int) else 0
    lk = r["likes"] if isinstance(r.get("likes"), int) else 0
    cl = r["collections"] if isinstance(r.get("collections"), int) else 0
    sp = 30 if r.get("staff_pick") else 0
    return sp + dl + 3 * lk + 2 * cl + 5 * r.get("score", 0)


# ---------------------------------------------------------------------------
# Main search flow
# ---------------------------------------------------------------------------

def search(query: str, source: str = "auto", limit: int = 6, order: str = "score") -> dict:
    import threading

    layers_used = []
    results = []

    # In auto mode the official search and the Printables complement run in
    # PARALLEL: the Printables layer is often unreachable behind the GFW and
    # burns its full 8s timeout — running it serially turned every auto query
    # into official_time + 8s (bitten 2026-09-13). Parallel keeps the
    # end-to-end latency at max(layers), not sum(layers).
    t0 = time.time()
    official_res = {}
    printables_res = {}
    official_total = 0

    def _run_official():
        official_res["got"] = _official_search(query, limit=limit * 2, order=order)

    def _run_printables():
        try:
            printables_res["got"] = _printables_api_impl(query, limit)
        except Exception as e:
            printables_res["got"] = []
            printables_res["err"] = f"{type(e).__name__}: {str(e)[:70]}"

    if source in ("auto", "cn", "intl"):
        th_off = threading.Thread(target=_run_official, daemon=True)
        th_off.start()
    if source == "auto":
        th_pr = threading.Thread(target=_run_printables, daemon=True)
        th_pr.start()
    elif source == "printables":
        _run_printables()

    if source in ("auto", "cn", "intl"):
        th_off.join()
        got = official_res.get("got", {"total": 0, "hits": [], "error": "thread lost"})
        official_total = got["total"]
        layers_used.append(
            {
                "layer": "official_search",
                "results": len(got["hits"]),
                "total_matches": got["total"],
                "elapsed_s": round(time.time() - t0, 2),
                "error": got["error"],
            }
        )
        results.extend(got["hits"])

    if source == "auto":
        th_pr.join()
        got = printables_res.get("got", [])
        layers_used.append({"layer": "printables_api", "results": len(got),
                            "error": printables_res.get("err", "")})
        results.extend(got)
    elif source == "printables":
        got = printables_res.get("got", [])
        layers_used.append({"layer": "printables_api", "results": len(got),
                            "error": printables_res.get("err", "")})
        results.extend(got)

    # Second pass: fill summary + translated title via design-service (staggered,
    # single global 12s budget — light-touch, ≤ limit calls, not batch scraping)
    mw_rows = [r for r in results if r.get("official")]
    def _fill_summary(r, delay):
        time.sleep(delay)
        m = re.search(r"models/(\d+)", r["url"])
        if not m:
            return
        meta = _official_meta(m.group(1))
        if meta:
            # NOTE: only fill the summary here. Do NOT override r["title"] —
            # design-service titleTranslated machine-translates Chinese models
            # into English, destroying the original title the user searched for
            # (bitten 2026-09-05: 「GAME BOY EDC 磁力推牌」→ "GAME BOY EDC Magnetic Pusher").
            if meta.get("summary"):
                r["desc"] = meta["summary"]

    ths = []
    for i, r in enumerate(mw_rows[:limit]):
        ths.append(threading.Thread(target=_fill_summary, args=(r, 0.08 * i), daemon=True))
    for t in ths:
        t.start()
    deadline = time.time() + 12
    for t in ths:
        t.join(timeout=max(0.0, deadline - time.time()))

    # Heuristic signals + final rank
    for r in results:
        r["score"], r["signals"] = _quality_signal(r)
        r["final_score"] = _rank_key(r)

    # Official-search rows keep API relevance order (Bambu's algorithm > our
    # popularity formula); they're placed above complement rows. Complement rows
    # (Printables) sort by final_score among themselves.
    official_rows = [r for r in results if r.get("official")]
    complement_rows = [r for r in results if not r.get("official")]
    complement_rows.sort(key=lambda r: -r["final_score"])
    results = official_rows + complement_rows

    return {
        "query": query,
        "mode": source,
        "order": order,
        "total": len(results),  # rows returned to the agent (official + complement)
        "matched_total": official_total,  # official relevance engine's match count
        "official_search_hits": len(official_rows),
        "layers": layers_used,
        "results": results[: limit * 3],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*", help="search keywords (L1 output)")
    ap.add_argument("--source", default="auto", choices=["auto", "cn", "intl", "printables"])
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--order", default="score", choices=list(ORDER_BY.keys()),
                    help="score=relevance (default) | hot | downloads | likes | new | boosts")
    ap.add_argument("--meta", help="fetch official metadata for a single model URL")
    args = ap.parse_args()

    if args.meta:
        print(json.dumps(_meta_single(args.meta), ensure_ascii=False, indent=2))
        return

    q = " ".join(args.query).strip()
    if not q:
        print(json.dumps({"error": "empty query"}, ensure_ascii=False))
        return
    out = search(q, args.source, args.limit, args.order)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()