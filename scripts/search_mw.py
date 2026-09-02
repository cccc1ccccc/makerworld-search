#!/usr/bin/env python3
"""
makerworld-search — v2 pipeline: ddgs discovery + official design-service enrichment.

Usage:
  python3 search_mw.py "phone stand" [--source auto|cn|intl|printables|plain] [--limit 6]
  python3 search_mw.py --meta "https://makerworld.com/en/models/717070-phone-stand"

Architecture (v2, parallel): discovery via ddgs site: search (cn/intl/printables
layers run in parallel threads, each with its own time budget), then every
MakerWorld candidate is enriched via the official design-service API (real
download/like/collect counts, no token). Heuristic signals only rank results
that got no official data. `--source plain` = open-web search (no site:
filter) keeping only model-page links — rescue layer for cold-start queries.
Output: JSON to stdout (agent consumes and renders L3 cards).
"""

import argparse
import json
import re
import sys
import time
from urllib.parse import urlparse

import requests

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

SITE_CN = "makerworld.com.cn"
SITE_INTL = "makerworld.com"
MW_URL_RE = re.compile(r"makerworld\.com(?:\.cn)?/(?:[a-z-]+/)?models/(\d+)-?([^/?#]*)")
PRINTABLES_URL_RE = re.compile(r"printables\.com/model/(\d+)")

# Official (undocumented but public) Bambu design-service endpoint — reverse-engineered
# pattern documented by Bambuddy wiki (upstream credit: Pr0zak/YASTL#51).
# Returns 65 fields incl. real downloadCount/likeCount/collectionCount + coverUrl.
DESIGN_API = "https://api.bambulab.com/v1/design-service/design/{design_id}"


def _official_meta(design_id: int | str, timeout: int = 15) -> dict | None:
    """Fetch official public metadata for one design. No token needed.

    Returns dict with title/downloads/likes/cover etc, or None on failure.
    This is the HIGHEST-priority data source: real counts, official fields.
    """
    try:
        r = requests.get(DESIGN_API.format(design_id=design_id), headers=UA, timeout=timeout)
        if r.status_code != 200:
            return None
        d = r.json()
        if not isinstance(d, dict) or "id" not in d:
            return None
        import html as _html

        def _strip(s):
            if not s:
                return ""
            s = re.sub(r"<[^>]+>", " ", str(s))
            return _html.unescape(re.sub(r"\s+", " ", s)).strip()

        creator = d.get("designCreator") or {}
        # tags can be a mix of dicts ({name:...}) and plain strings
        tags = []
        for t in (d.get("tags") or []):
            if isinstance(t, dict):
                tags.append(t.get("name") or t.get("nameTranslated") or "")
            elif isinstance(t, str):
                tags.append(t)
        cats = []
        for c in (d.get("categories") or []):
            if isinstance(c, dict):
                cats.append(c.get("name") or "")
            elif isinstance(c, str):
                cats.append(c)
        return {
            "id": d.get("id"),
            "title": d.get("titleTranslated") or d.get("title") or "",
            "slug": d.get("slug") or "",
            "cover": d.get("coverUrl") or "",
            "summary": _strip(d.get("summaryTranslated") or d.get("summary"))[:240],
            "downloads": d.get("downloadCount"),
            "likes": d.get("likeCount"),
            "collections": d.get("collectionCount"),
            "prints": d.get("printCount"),
            "comments": d.get("commentCount"),
            "author": creator.get("name") or creator.get("nickName") or "",
            "staff_pick": bool(d.get("isStaffPicked")),
            "license": d.get("license") or "",
            "tags": [t for t in tags if t][:8],
            "categories": [c for c in cats if c][:4],
        }
    except Exception:
        return None


def _ddg_site(query: str, site: str, limit: int, retries: int = 2) -> list:
    """ddgs site:-restricted search. NOTE: the ddgs package rotates backends
    (DDG/Brave/...) — the error messages show search.brave.com requests, so
    rate-limit behavior is "strictest backend wins", not duckduckgo.com's."""
    if not DDGS_AVAILABLE:
        raise RuntimeError("ddgs not installed: pip install ddgs")
    q = f"site:{site} {query}"
    results = []
    for attempt in range(retries):
        try:
            raw = DDGS().text(q, max_results=limit * 3, timeout=12)
            for r in raw:
                # strip ?from=search / #anchor noise before storing
                url = (r.get("href") or "").split("?")[0].split("#")[0]
                title = r.get("title") or ""
                body = r.get("body") or ""
                if site not in url:
                    continue
                # Keep only real model pages; drop collections/users/search pages.
                # Any language prefix is fine on both sites — variants merge by
                # design_id later (a /zh/-only regex would silently drop
                # makerworld.com.cn/en/... pages DDG happens to index).
                if site.endswith(".cn"):
                    ok = re.search(r"makerworld\.com\.cn/(?:[a-z-]+/)?models/\d+", url)
                else:
                    ok = re.search(r"makerworld\.com/(?:[a-z-]+/)?models/\d+", url)
                if not ok or "/search" in url:
                    continue
                results.append(
                    {"url": url, "title": title, "source": site, "desc": body.strip()[:220]}
                )
                if len(results) >= limit:
                    break
            break
        except Exception:
            time.sleep(1.0)
    return results[:limit]


def _ddg_plain(query: str, limit: int, retries: int = 2) -> list:
    """Open-web ddgs search (no site: filter), keep only MakerWorld/Printables
    model pages. Rescue layer for cold-start queries site:-search misses."""
    if not DDGS_AVAILABLE:
        raise RuntimeError("ddgs not installed: pip install ddgs")
    results = []
    for attempt in range(retries):
        try:
            raw = DDGS().text(query, max_results=limit * 5, timeout=12)
            for r in raw:
                url = (r.get("href") or "").split("?")[0].split("#")[0]
                site = None
                if MW_URL_RE.search(url) and "/search" not in url:
                    site = "makerworld.com.cn" if ".cn" in url else "makerworld.com"
                elif PRINTABLES_URL_RE.search(url):
                    site = "printables.com"
                if not site:
                    continue
                results.append(
                    {
                        "url": url,
                        "title": r.get("title") or "",
                        "source": site,
                        "desc": (r.get("body") or "").strip()[:220],
                    }
                )
                if len(results) >= limit:
                    break
            break
        except Exception:
            time.sleep(1.0)
    return results[:limit]


def _printables_api(query: str, limit: int) -> list:
    """Printables public GraphQL API — best field coverage in the chain."""
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
        r = requests.post(endpoint, json=payload, headers=UA, timeout=20)
        if r.status_code != 200:
            return []
        data = r.json()
        edges = data.get("data", {}).get("print", {}).get("edges", [])
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
                    "downloads": n.get("downloadsCountAllTime"),
                    "likes": n.get("likesCountAllTime"),
                    "image": img,
                }
            )
        return out[:limit]
    except Exception:
        return []


def _meta_single(url: str) -> dict:
    """Try to fetch og: metadata from a single model page. 403 → return gracefully."""
    out = {"url": url, "og_title": None, "og_image": None, "og_description": None, "fetched": False}
    try:
        r = requests.get(url, headers=UA, timeout=15)
        if r.status_code != 200:
            out["http_status"] = r.status_code
            return out
        t = r.text
        for key in ("og:title", "og:image", "og:description"):
            m = re.search(r'<meta[^>]*property="{}"[^>]*content="([^"]+)"'.format(key), t)
            if m:
                out[key.replace(":", "_")] = m.group(1)[:300]
        out["fetched"] = True
    except Exception as e:
        out["error"] = str(e)[:100]
    return out


def _clean_desc(desc: str, source: str) -> str:
    """Strip page-chrome noise from DDG body snippets (nav links, author rows, boilerplate)."""
    t = desc
    t = re.sub(r"Download this free 3D print file designed by [\w\-\.]+\.?", "", t)
    t = re.sub(r"MakerWorld is the leading[^.]*\.", "", t)
    # nav junk common on makerworld pages
    t = re.sub(r"(关注|已发布|相关模型|收藏夹|下载模型|更多模型|返回|举报)", " ", t)
    t = re.sub(r"by user_[\w]+", " ", t)
    t = re.sub(r"[A-Za-z0-9_-]+\.?\s*\d*\.?\s*[\d.]+\s*[kKmM]?\s*$", " ", t)  # trailing counts
    t = re.sub(r"\s{2,}", " ", t).strip(" .、,")
    return t[:200]


def _quality_signal(r: dict) -> tuple:
    """Heuristic quality signals extractable without hitting the site.

    DDG gives us no download/like counts (CF blocks direct pages), but titles and
    descs leak real signals. Returns (score, signals:list) — higher is better.
    """
    title = (r.get("title") or "").lower()
    desc = (r.get("desc") or "").lower()
    text = title + " " + desc
    score = 0
    signals = []

    # 1. Author credit in title ("by Xxx") — popular models usually carry it in DDG index
    #    user_<digits> throwaway accounts don't count.
    m = re.search(r"\bby\s+([a-z0-9_\-.]{2,20})$", title)
    if m and not re.match(r"^user_\d+$", m.group(1)):
        score += 2
        signals.append("具名作者")

    # 2. Popularity counts leaked into desc ("4.5k", "1.2 M downloads" style)
    m = re.findall(r"(\d+(?:\.\d+)?)\s*k\b", text)
    if m:
        top_k = max(float(x) for x in m)
        score += 1 + min(int(top_k), 5)  # 4.5k ≈ +5, 0.5k ≈ +1
        signals.append(f"热度{top_k}k级")
    big = re.search(r"(\d{3,})\s*(?:downloads?|下载)", text)
    if big:
        score += 2
        signals.append("高下载量")

    # 3. Print-practical keywords in desc — signals a maintained, usable model
    for kw, w in [("no support", 2), ("无支撑", 2), ("ams", 1), ("multicolor", 1),
                  ("多色", 1), ("parametric", 2), ("参数化", 2), ("customizer", 2),
                  ("test print", 2), ("实测", 2), ("已优化", 2), ("optimized", 2)]:
        if kw in text:
            score += w
            signals.append(kw)

    # 4. Language match bonus is NOT scored here (agent decides per user language)
    return score, signals


def _dedup(results: list) -> list:
    seen = set()
    out = []
    for r in results:
        p = urlparse(r["url"])
        key = (p.netloc, re.sub(r"[?#].*$", "", p.path))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _clean_title(title: str, source: str) -> str:
    """Strip 'MakerWorld: ...' / ' - Printables' tails that DDG keeps in titles."""
    t = title
    # Loop: DDG titles can carry multiple tails ("X - 免费 3D 打印模型 - MakerWorld")
    for _ in range(3):
        t2 = t
        t2 = re.sub(r"\s*-\s*免费 3D 打印模型\s*$", "", t2)
        t2 = re.sub(r"\s*-\s*免費 3D 列印模型\s*$", "", t2)
        t2 = re.sub(r"\s*-\s*Free 3D Print Model\s*$", "", t2)
        t2 = re.sub(r"\s*-\s*MakerWorld[：:]?\s*.*$", "", t2)
        t2 = re.sub(r"\s*-\s*Printables\.com\s*.*$", "", t2)
        t2 = re.sub(r"\s*来自\s+[\w\.\-]+\s*MakerWorld[：:]?\s*.*$", "", t2)
        t2 = re.sub(r"\s+MakerWorld[：:]\s*.*$", "", t2)
        if t2 == t:
            break
        t = t2
    t = t.strip()
    return t if len(t) >= 3 else title.strip()


def search(query: str, source: str = "auto", limit: int = 6) -> dict:
    layers_used = []
    all_results = []

    def run_layer(name, fn, seconds=25):
        """Run one retrieval layer in a thread; results land in all_results/layers_used."""
        got = []
        err = ""
        try:
            got = run_with_timeout(fn, seconds)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:70]}"
            print(f"[_run_layer] {name} failed/timeout: {err}", file=sys.stderr)
        layers_used.append({"layer": name, "results": len(got), "error": err})
        all_results.extend(got)

    import threading

    def run_with_timeout(fn, seconds):
        """Run fn with a hard time budget, surfacing inner exceptions (a raise
        inside the thread previously died silently → invisible empty layer)."""
        box = {}

        def _target():
            try:
                box["ok"] = fn()
            except Exception as e:
                box["err"] = f"{type(e).__name__}: {str(e)[:70]}"

        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(seconds)
        if "err" in box:
            raise RuntimeError(box["err"])
        if t.is_alive():
            raise TimeoutError(f"layer exceeded {seconds}s")
        return box.get("ok", [])

    jobs = []
    if source in ("auto", "cn"):
        jobs.append(("makerworld.com.cn", lambda: _ddg_site(query, SITE_CN, limit)))
    if source in ("auto", "intl"):
        jobs.append(("makerworld.com", lambda: _ddg_site(query, SITE_INTL, limit)))
    if source in ("auto", "printables"):
        jobs.append(("printables_api", lambda: _printables_api(query, limit)))
    if source == "plain":
        jobs.append(("ddg_plain", lambda: _ddg_plain(query, limit)))

    threads = [threading.Thread(target=run_layer, args=(n, f), daemon=True) for n, f in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    results = _dedup(all_results)
    # Merge same-design language variants (en/ru/zh paths) by design_id
    by_id = {}
    merged = []
    for r in results:
        m = re.search(r"makerworld\.com(?:\.cn)?/(?:[a-z-]+/)?models/(\d+)", r["url"])
        if m and "makerworld" in r.get("source", ""):
            did = m.group(1)
            if did in by_id:
                # prefer zh/cn variant as canonical, keep other as alt URL
                if ".cn" in r["url"] and ".cn" not in by_id[did]["url"]:
                    r2 = by_id[did]
                    r["alt_urls"] = [r2["url"]] + r2.get("alt_urls", [])
                    by_id[did] = r
                    idx = merged.index(r2)
                    merged[idx] = r
                else:
                    r2 = by_id[did]
                    r2.setdefault("alt_urls", []).append(r["url"])
                continue
            by_id[did] = r
        merged.append(r)
    results = merged

    for r in results:
        r["title"] = _clean_title(r["title"], r["source"])
        if r.get("desc"):
            r["desc"] = _clean_desc(r["desc"], r["source"])

    # === L0 official enrichment: for every MakerWorld result, hit the official
    # design-service API (no token needed) to get REAL download/like/collect
    # counts + cover image + tags. DDG only discovered the URL; official data
    # enriches and re-ranks it. ===
    official_ok = 0
    mw_results = [r for r in results if "makerworld.com" in r.get("source", "")]
    ids = []
    for r in mw_results:
        m = re.search(r"models/(\d+)", r["url"])
        if m:
            ids.append((r, m.group(1)))

    def _enrich(r, did):
        meta = _official_meta(did)
        if meta:
            r["official"] = meta
            # Title from official API is cleaner than DDG's
            if meta.get("title"):
                r["title"] = meta["title"]
            if meta.get("summary"):
                r["desc"] = meta["summary"]

    import threading as _t

    def _enrich_staggered(r, did, delay):
        time.sleep(delay)
        _enrich(r, did)

    en_threads = []
    for i, (r, did) in enumerate(ids):
        # 80ms stagger: 20 simultaneous hits on the design-service API could
        # look like a burst; spreading starts over ~1.5s keeps us polite.
        en_threads.append(_t.Thread(target=_enrich_staggered, args=(r, did, 0.08 * i), daemon=True))
    for th in en_threads:
        th.start()
    # single global budget: sequential th.join(timeout=12) would stack to 12s*N
    # worst-case with slow threads; joining against one deadline caps enrichment
    # at ~15s total regardless of candidate count.
    deadline = time.time() + 15
    for th in en_threads:
        th.join(timeout=max(0.0, deadline - time.time()))
    official_ok = sum(1 for r in results if r.get("official"))

    # === Ranking: real official counts dominate; heuristic signals only fill gaps ===
    # Heuristic quality signals (author credit, popularity leak in desc, print-practical
    # keywords) apply to ALL results — for officially-enriched ones they're a minor tie
    # breaker (5x), for un-enriched ones (API failed / Printables cold rows) they're
    # the only ranking signal. Computed here because score/signals were previously
    # never populated (dead code — found in 2026-09-02 audit).
    for r in results:
        r["score"], r["signals"] = _quality_signal(r)

    def _rank_key(r):
        off = r.get("official") or {}
        # official API first; fall back to top-level counts (Printables rows carry
        # downloads/likes at top level — _rank_key previously missed them entirely)
        dl = off.get("downloads") if isinstance(off.get("downloads"), int) else (r.get("downloads") or 0)
        lk = off.get("likes") if isinstance(off.get("likes"), int) else (r.get("likes") or 0)
        cl = off.get("collections") if isinstance(off.get("collections"), int) else (r.get("collections") or 0)
        sp = 30 if off.get("staff_pick") else 0
        # popularity = downloads + 3*likes + 2*collections + staff-pick boost
        return sp + dl + 3 * lk + 2 * cl + 5 * r.get("score", 0)

    for r in results:
        r["final_score"] = _rank_key(r)
    results.sort(key=lambda r: -r["final_score"])

    return {
        "query": query,
        "mode": source,
        "total": len(results),
        "official_enriched": official_ok,
        "layers": layers_used,
        "results": results,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*", help="search keywords (L1 output)")
    ap.add_argument("--source", default="auto", choices=["auto", "cn", "intl", "printables", "plain"])
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--meta", help="fetch og metadata for a single model URL")
    args = ap.parse_args()

    if args.meta:
        print(json.dumps(_meta_single(args.meta), ensure_ascii=False, indent=2))
        return

    q = " ".join(args.query).strip()
    if not q:
        print(json.dumps({"error": "empty query"}, ensure_ascii=False))
        return
    out = search(q, args.source, args.limit)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()