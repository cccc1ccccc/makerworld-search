# makerworld-search

**A natural-language semantic search skill for [MakerWorld](https://makerworld.com) (Bambu Lab's 3D-print model community) — for any AI agent.**

> Say *"find me a pegboard cable holder"* or *"搜一个怪物猎人冰箱贴"* — the agent rewrites your intent into bilingual keyword groups, discovers candidate models, enriches every candidate with **real official data** (downloads / likes / collections / staff-pick) via Bambu's design-service endpoint, and hands you a shortlist that actually matches what you meant.

[architecture diagram](docs/architecture.png)

## Why

MakerWorld has no public search API. Community skills in this space are all printer-control; **model search is a 0-competitor niche**. Meanwhile, search engines only keyword-match — *"挂洞洞板的数据线收纳"* finds nothing. This skill closes both gaps:

- **L1 semantic rewrite** (the agent itself): intent → 2–4 bilingual keyword groups
- **L2 discovery** (`search_mw.py`): parallel `site:` search across makerworld.com / .cn / Printables, 25s budget per layer, visible per-layer errors
- **L0 official enrichment** (built-in): every candidate's design_id → `api.bambulab.com/v1/design-service/design/{id}` (no token, 65 fields) → real download/like/collection counts, cover, tags, staff-pick flag
- **L3 intent gatekeeping** (the agent again): ranking is a candidate pool — the agent checks title/summary/tags against your actual intent before showing top 3–5

Ranking formula: `final_score = downloads + 3×likes + 2×collections + 30×staff_pick + 5×heuristic`

## Install

Works with any agent that reads the [Agent Skills](https://github.com/anthropics/skills) convention (Claude Code, OpenClaw, Cursor, Hermes, …). Drop the folder into your agent's skills directory, then:

```bash
pip install requests ddgs
```

No API keys. No login. No hardware required.

## Usage

```bash
# single keyword group
python3 scripts/search_mw.py "phone stand" --limit 6
# Chinese site / international site / open-web rescue / Printables
python3 scripts/search_mw.py "手机支架" --source cn
python3 scripts/search_mw.py "pegboard cable holder" --source intl
python3 scripts/search_mw.py "mario pegboard" --source plain
# metadata for one known URL
python3 search_mw.py --meta "https://makerworld.com/en/models/717070-phone-stand"
```

The agent side of the protocol (L1 rewrite rules, L3 gatekeeping checklist, card format) lives in [SKILL.md](SKILL.md).

## Provenance & compliance

- The design-service endpoint is **undocumented but public** (plain GET, no auth). Reverse-engineering pattern first published by the **[Bambuddy](https://github.com/maziggy/bambuddy) wiki** (upstream credit: Pr0zak / YASTL#51). This project uses it for **single-call-per-design metadata enrichment only** — no batch scraping, no auth bypass, no file downloads.
- Discovery uses the `ddgs` package (DuckDuckGo/Brave backends). On CN networks DDG may rate-limit; Printables may be unreachable (GFW). The pipeline degrades gracefully either way.
- MakerWorld model downloads require login by design — this skill gives you the link; you click it.
- Community context: users have long requested an official MakerWorld API ([forum #205669](https://forum.bambulab.com/t/makerworld-api/205669)); none is planned. This skill is a community bridge until one exists.

## Verified runs

| Query | Result |
|---|---|
| SKÅDIS cable holder | 20 deduped, top-10 all relevant; staff-pick winner 8.4k dl / 18.3k collections |
| EDC 推牌 (fidget sliders) | 14 deduped, 4 precision hits |
| Mario × pegboard | 17 deduped; top hit staff-pick + 18,302 collections |
| Monster Hunter keychain/magnet | 5 precision hits; L3 gatekeeping dropped 5 off-topic high-pagerank decoys |

## License

MIT — see [SKILL.md](SKILL.md) frontmatter. Endpoint credit: Bambuddy wiki / Pr0zak (YASTL#51).

---

# makerworld-search（中文说明）

**给任何 AI agent 用的 MakerWorld（拓竹模型社区）自然语言搜索 skill。**

你说「找一个挂洞洞板的数据线收纳」，agent 把意图改写成中英双语关键词组 → 三站并行发现候选 → 官方 design-service 端点给每个候选补上**真实下载/点赞/收藏数**（无需 token）→ 按意图把关后给出真正对口的 3–5 个结果。

MakerWorld 没有公开搜索 API，社区 skill 全是打印控制类——**模型搜索是空白赛道**。这个 skill 用「agent 语义改写 + 官方真实数据 + 意图把关」三层组合补上这个缺口。

**安装**：把本目录放进你的 agent 的 skills 目录，`pip install requests ddgs`，无需任何 key 或登录。

**合规**：官方端点只做单次元数据增强（出处见 Bambuddy wiki），不批量抓取、不代下载、不绕验证。模型文件下载需登录，skill 只给链接。