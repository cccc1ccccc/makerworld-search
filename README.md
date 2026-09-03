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
python3 scripts/search_mw.py --meta "https://makerworld.com/en/models/717070-phone-stand"
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

**给任何 AI agent 用的 [MakerWorld](https://makerworld.com)（拓竹模型社区）自然语言搜索 skill。**

> 说「找一个挂洞洞板的数据线收纳」或 *"find me a Monster Hunter keychain"* — agent 把你的意图改写成中英双语关键词组，发现候选模型，再通过拓竹官方 design-service 端点给每个候选补上**真实数据**（下载/点赞/收藏/官方精选），交给你一份真正对口的候选清单。

[架构图](docs/architecture.png)

## 为什么做这个

MakerWorld 没有公开搜索 API。这个领域的社区 skill 全是打印机控制类——**模型搜索是空白赛道**。而搜索引擎只会关键词匹配——搜「挂洞洞板的数据线收纳」什么都找不到。这个 skill 同时补上两个缺口：

- **L1 语义改写**（agent 自己做）：意图 → 2-4 组中英双语关键词组
- **L2 发现层**（`search_mw.py`）：并行 `site:` 检索 makerworld.com / .cn / Printables，每层 25s 超时预算，每层失败原因可见
- **L0 官方数据增强**（脚本内置）：每个候选的 design_id → `api.bambulab.com/v1/design-service/design/{id}`（无需 token，65 字段）→ 真实下载/点赞/收藏数、封面、tags、官方精选标记
- **L3 意图把关**（agent 自己做）：排序结果只是候选池——agent 按你的实际意图核对标题/简介/tags 后才输出 top 3-5

排序公式：`final_score = 下载 + 3×赞 + 2×藏 + 30×官方精选 + 5×启发式兜底`

## 安装

适配任何遵循 [Agent Skills](https://github.com/anthropics/skills) 约定的 agent（Claude Code、OpenClaw、Cursor、Hermes 等）。把本目录放进你 agent 的 skills 目录，然后：

```bash
pip install requests ddgs
```

无需 API key。无需登录。无需打印机。

## 用法

```bash
# 单组关键词搜索
python3 scripts/search_mw.py "phone stand" --limit 6
# 中文站 / 国际站 / 开放网络兜底 / Printables
python3 scripts/search_mw.py "手机支架" --source cn
python3 scripts/search_mw.py "pegboard cable holder" --source intl
python3 scripts/search_mw.py "mario pegboard" --source plain
# 已知 URL 提取元数据
python3 scripts/search_mw.py --meta "https://makerworld.com/en/models/717070-phone-stand"
```

协议中 agent 侧的部分（L1 改写规则、L3 把关清单、卡片格式）在 [SKILL.md](SKILL.md)。

## 出处与合规

- design-service 端点是**未文档化的公开接口**（纯 GET，无鉴权）。逆向模式首发表于 **[Bambuddy](https://github.com/maziggy/bambuddy) wiki**（上游：Pr0zak / YASTL#51）。本项目仅将其用于**单模型单次元数据增强**——不批量抓取、不绕验证、不代下载文件。
- 发现层用 `ddgs` 包（DuckDuckGo/Brave 后端）。国内网络 DDG 可能限流；Printables 可能不可达（墙）。管线在两种情况下都会优雅降级。
- MakerWorld 模型下载按官方设计需登录——skill 给你链接，你自己点。
- 社区背景：用户长期呼吁官方出 MakerWorld API（[forum #205669](https://forum.bambulab.com/t/makerworld-api/205669)）；官方无计划。在官方 API 出现前，本 skill 是社区桥接方案。

## 实测记录

| 查询 | 结果 |
|---|---|
| SKÅDIS 数据线收纳 | 去重后 20 个，top-10 全部相关；官方精选第一名的 8.4k 下载 / 18.3k 收藏 |
| EDC 推牌（fidget sliders） | 去重后 14 个，4 个精准命中 |
| 马里奥 × 洞洞板 | 去重后 17 个；第一名官方精选 + 18,302 收藏 |
| 怪物猎人钥匙扣/冰箱贴 | 5 个精准命中；L3 把关剔除 5 个高 pagerank 的跑题引流模型 |

## 许可

MIT — 见 [SKILL.md](SKILL.md) frontmatter。端点出处：Bambuddy wiki / Pr0zak (YASTL#51)。