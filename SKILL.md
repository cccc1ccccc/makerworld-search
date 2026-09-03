---
name: makerworld-search
description: "Natural-language semantic search for 3D printable models across MakerWorld (Bambu Lab community) and fallback sources. Activate when user wants to find/discover/download 3D models, e.g. 'find me a pegboard cable holder', '找一个手机支架', '找模型'. Pipeline: L1 intent→keyword rewrite (bilingual) → L2 discovery via DDG site-search → L0 official design-service API enrichment (real download/like/collect counts + cover + tags, no token) → L3 result cards with real-data ranking."
version: "0.4.0"
license: MIT
keywords:
  - 3d model search
  - makerworld
  - semantic search
  - find models
  - stl search
---

# 🔎 MakerWorld 语义搜索

用户一句话 → L1 语义改写 → L2 DDG 发现 → L0 官方数据增强 → L3 结果卡片

**架构原则（用户明确指示）：官方数据路径最高优先级，DDG 只是发现层/降级方案。**
检索引擎只会关键词匹配；本 skill 用多组中英双语检索词发现候选，再用**官方 design-service API**（无需 token）拿真实下载数/点赞/封面/tags 增强每个候选，最后由 agent 按意图把关排序。核心创新 = L1 意图理解 × L0 官方真实数据。

---

## Pipeline（每次查询必走）

```
用户需求（自然语言）
   │
   ▼
[L1 语义改写]（agent 自己做，不调脚本）
   - 提取：物体类型 + 关键属性（尺寸/接口/用途/风格）
   - 输出 2-4 组关键词：中文组 + 英文组 + 同义词组
   - 例："挂洞洞板的数据线收纳"
     → ["洞洞板 数据线 收纳", "SKÅDIS cable holder", "pegboard cable organizer", "wall cable management"]
   │
   ▼
[L2 发现层] python3 scripts/search_mw.py "关键词" [--source auto]
   - ddgs site: 检索只负责"发现候选 URL + design_id"——数据不从这里来
   - 注意：ddgs 包会轮换后端（DDG/Brave），报错显示 search.brave.com 属正常
   - 三层并行执行：makerworld.com.cn + makerworld.com + printables 同时开跑
   - 每层独立 25s 超时预算（threading），失败原因记录在 layers[].error（不再静默）
   - 同 design_id 的 en/ru/zh 语言变体自动归并（脚本内置）
   - `--source plain` = 开放网络搜索兜底（无 site: 限制，只留模型页）——site: 搜不到的冷门查询用它
   │
   ▼
[L0 官方数据层]（脚本内置，agent 不用管）
   - 对每个候选 design_id 调官方 design-service API（无需 token）
   - 拿真实下载数/点赞/收藏/打印数 + 封面图 URL + tags + 官方精选标记
   - 官方数据覆盖 DDG 的标题/简介（更干净、带中文翻译）
   - final_score = 下载 + 3×赞 + 2×藏 + 30×官方精选 + 5×启发式兜底
   │
   ▼
[L3 结果卡片]（agent 自己做，不调脚本）
   - 官方数据排序结果作为候选池，按意图挑 top 3-5
   - 输出卡片：标题 / 真实下载·赞·藏数 / 封面 / 链接 / 匹配理由
   - 附加：问用户"看中哪个？我可以直接下载→改尺寸→上色"
```

## Quick Reference

| 想做什么 | 命令 |
|---|---|
| 单组关键词搜索 | `python3 scripts/search_mw.py "phone stand" --limit 6` |
| 指定中文站 | `python3 scripts/search_mw.py "手机支架" --source cn` |
| 指定国际站 | `python3 scripts/search_mw.py "pegboard cable holder" --source intl` |
| Printables API | `python3 scripts/search_mw.py "cable clip" --source printables` |
| 开放网络兜底（冷门查询） | `python3 scripts/search_mw.py "mario pegboard" --source plain` |
| 全链自动 | `python3 scripts/search_mw.py "洞洞板 数据线" --source auto` |
| 从 URL 提元数据 | `python3 scripts/search_mw.py --meta "https://makerworld.com/en/models/717070-phone-stand"` |

## L1 改写协议（agent 必读）

改写时遵循的规则，按优先级：

1. **物体类型放最前**：支架/收纳/钩子/外壳/玩具 → 类别词是检索主干
2. **接口/标准件用专名**：SKÅDIS(不用"洞洞板")、M3、2020/3030型材、VESA、GoPro、USB-C
3. **中英都出**：中文站和英文站收录内容不同，双语言各搜一组
4. **同义词兜底**：holder/clip/organizer/mount/stand 常互换，挑 1-2 个变体
5. **别堆砌**：每组关键词 ≤4 个词，多了搜索引擎反而失焦

典型改写示例（存入脑内，遇到类似需求直接套）：

| 用户说 | 改写为 |
|---|---|
| 挂洞洞板的数据线收纳 | SKÅDIS cable holder / pegboard cable organizer / 洞洞板 数据线 |
| 打印机旁放耗材的小架子 | AMS filament holder / spool holder / 耗材架 |
| 摄影灯的1/4接口底座 | camera 1/4 mount / light mount tripod |
| 遥控器收纳 | remote holder / remote control organizer |
| 隐藏在桌下的走线 | under desk cable management / desk cable clip |

更多实测改写模式（含 EDC 推牌场景）见 `references/rewrite-patterns.md`。

## Implementation Notes (from real tests, 2026-09-02)

- **DDG `site:` search is the discovery workhorse** — both makerworld.com and makerworld.com.cn are well indexed; Chinese queries work on the .cn site, English on .com. Multi-query rewriting (4 keyword groups) expanded a single 6-result query into 20 deduplicated results — this is the core value of L1.
- **Filter to real model pages** — DDG returns collections/`@user/following`/search pages too; regex-filter to `/models/\d+` URLs only (script does this).
- **Chinese DDG queries are slow** (30s+ per layer) — `--limit 4` per keyword group, `timeout=15` on DDGS calls, 1s between retries. Don't stack many Chinese groups.
- **og: metadata fetch will likely 403** (Cloudflare, probabilistic) — the script degrades gracefully to `fetched:false`; never retry hard. L0 official API now supplies covers, so og: is legacy.
- **Printables GraphQL API** has rich fields but Prusa-ecosystem content — use as a complement, not a replacement. On this network it may be entirely unreachable (see 工程笔记).

## L2 降级链设计（为什么这么做）

实测（2026-09-02，详见 references/feasibility.md）：
- makerworld.com 无公开搜索 API；Cloudflare 概率性 403（数据中心 IP 被标记）
- 但 **DDG 对 makerworld.com 和 makerworld.com.cn 收录都很好**，site: 搜索能拿到具体模型页
- Printables 有公开 GraphQL API，字段全，但本网络环境可能不可达

**架构（v3）：发现靠 DDG，数据靠官方。** DDG 只出候选 URL；真实数据一律走 L0 官方端点。
**不硬刚 Cloudflare。** 单模型页 og: 元数据（--meta）拿到就锦上添花，拿不到不影响主流程。

## L3 卡片格式（输出给用户前先过一遍）

```
🔍 为你找到 N 个模型（按官方真实数据排序）：

1. **宜家SKADIS洞洞板 数据线收纳/理线器** ｜ MakerWorld 中文站
   📥 413 下载 · 👍 220 赞 · ⭐官方精选 · 封面: [URL]
   简介：卡在SKÅDIS洞洞板上的数据线收纳……（desc一句，官方summary截断）
   链接：https://makerworld.com.cn/zh/models/1270816-...
   匹配：正好是你要的"SKÅDIS+数据线收纳"，tags: 洞洞板/数据线/收纳

2. ...
```

- 每条必含：标题、链接、来源、真实数据（有 official 时）、**desc 一句话**、**一句话匹配理由**
- **official 字段路径（2026-09-03 实测踩坑，读错路径=dl 全显 0）**：官方数据在 `r["official"]` 嵌套对象里，键名是**短名**不是 API 原名：
  - `r["official"]["downloads"]` ← API `downloadCount`（❌不存在 `official.downloadCount`）
  - `r["official"]["likes"]` ← API `likeCount`；`r["official"]["collections"]` ← API `collectionCount`
  - `r["official"]["staff_pick"]` ← API `isStaffPicked`；另有 `title/summary/cover/tags/categories/author/license`
  - Printables 层的计数在**顶层** `r["downloads"]` / `r["likes"]`（无 official 对象）
  - 排序结果看 `r["final_score"]`，启发式明细看 `r["score"]`+`r["signals"]`
  - 写显示代码前先 dump 一条 `json.dumps(results[0], indent=2)` 确认路径，不要凭记忆写键名
- **数字显示用 `isinstance(n, int)` 判断，不要 `n or '?'`**——0 会被显示成 '?'
- **排序规则（两层）：** 脚本已按 final_score（官方真实数据+精选加权+启发式×5兜底）排序，但**热度 ≠ 意图匹配**——agent 必须把脚本排序当候选池，再按用户意图做最终排序。实测案例①：洞洞板本体 413 下载排第一，但用户要的是数据线收纳。实测案例②：「马里奥洞洞板」查询混入 Kakashi/McLaren/圣诞星——作者发布后改了标题，DDG 旧索引+URL slug 残留旧拼音触发召回（官方 API 的 title 与新内容一致，但召回源仍是旧的）。agent 输出前必须逐条判断「标题/简介/tags 与意图的相符度」，不符的剔除或排末位并说明
- **staff_pick 是金信号**：`official.staff_pick=true` 优先推荐（官方人工精选背书）。实测：马里奥查询第一名「Ikea Skadis Mario NEW DESIGN」精选+18,302收藏，final_score 断层领先，真实数据排序直接把爆款顶出来了
- 匹配理由必须基于标题/desc/官方 tags 推断，不许编造
- user_xxxxx 数字马甲用户名不算「具名作者」信号
- 结果 <2 个时主动建议：换关键词 / 走生成兜底（generate.py）

## 工程实测笔记（2026-09-02 调试沉淀）

### 0.4.0 全面审计修复（同日代码审查）

- **[死代码] `_quality_signal` 从未被调用**：v2 重构时漏了调用点，score/signals 字段从未生成，启发式兜底权重恒为 0。已修：search() 排序前统一计算 `r["score"], r["signals"] = _quality_signal(r)`
- **[功能失效] `--source plain` 指错函数**：实际跑的是 `_ddg_site(query, SITE_CN)`（=cn模式），不是开放搜索。已修：新增 `_ddg_plain()`（无 site: 限制，正则只留模型页）
- **[排序缺数] `_rank_key` 忽略 Printables 顶层计数**：Printables 结果的 downloads/likes 在顶层不在 official 字段，可达时会被全排到末位。已修：isinstance 回退链
- **[性能] enrichment join 逐个叠加**：`th.join(timeout=12)` × N 个候选最坏 12s×N；改全局 deadline 15s 封顶
- **[静默失败] 线程内异常被吞**：`box.update(ok=fn())` 里 fn 抛异常→层返回空且无痕迹（审计时 intl 层第一次 0 结果就是这么发生的）。已修：异常上抛 + `layers[].error` 字段
- **[正则过严] .cn 站只认 `/zh/`**：漏掉 DDG 索引的 makerworld.com.cn/en/ 变体页。已修：放宽为 `(?:[a-z-]+/)?`
- **[URL杂讯] `?from=search` 破坏去重**：同一模型带不同 query 参数会重复出现。已修：入库前剥 `?`/`#` 后缀
- **[合规] enrichment 80ms 错峰启动**：20 并发齐打官方 API 有 burst 观感，错峰 1.5s 内展开
- **[依赖] ddgs ImportError 改为启动时检测**（模块顶部 try-import），不再在线程里 print+exit 污染 JSON
- 已知权衡（非bug）：enriched 结果的 desc 被官方 summary 覆盖，启发式信号天然归零——启发式本就只服务「无官方数据」的兜底行

### 架构图（投稿展示素材）

`/mnt/d/makerworld_search_architecture.html`（+同名PNG）— 暗色科技风架构图，四层管线+双Agent把关+两条兜底路径，节点/连线/图例完整对应本 SKILL.md 的架构。生成与验证流程见 creative-diagrams skill 的 `references/svg-geometry-verification.md`（无vision环境的程序化几何QA）。若后续架构变更（如接入官方搜索API），需重跑该skill重新生成，别手改SVG坐标。

### 早期笔记（v1-v2 时代，仍有效）

- **DDG body 字段 = meta description 金矿**：不碰 Cloudflare 就能拿到每个模型的简介。`_clean_desc` 过滤「关注/相关模型/by user_xxx」等页面杂讯。（L0 上线后 desc 主要来自官方 summary，此为兜底）
- **三层必须并行**：串行 60s+ 交互不可用；threading 并行后端到端 ~20s（中文层最慢）
- **DDG 同 IP 连续查询会限流**：中文层偶发 0 结果多为此因。多组改写词之间天然有间隔，实际影响小
- **DDGS().text() 支持 timeout 参数**（timeout=12 实测有效），每层必须设
- **结果须过滤非模型页**：DDG site 搜索会混入收藏夹/用户主页/搜索页，用 `models/\d+` 正则过滤（已内置）
- **DDG images() 通道不可用**（超时失败且无模型-ID 关联）——封面图改由 L0 官方 coverUrl 提供
- **⚠️ Printables 层返回 0 的真因 = 网络封锁，不是 schema**：`api.printables.com` 在本机完全不可达（直连 Errno 101 + 本地代理口全 000）。**排查顺序：先 curl 探网络可达性，再怀疑 schema**
- **✅ L0 官方数据层已打通（同日下午推翻早前"真实数据拿不到"的硬结论）**：`GET api.bambulab.com/v1/design-service/design/{id}` 无需 token，65 字段含真实 downloadCount/likeCount/collectionCount + coverUrl + tags。出处：Bambuddy wiki 披露的逆向模式（上游 Pr0zak/YASTL#51）。详见 `references/design-service-api.md`
- **官方 API 解析陷阱**：tags 是 str 与 {name:...} dict 混合数组，必须 isinstance 分支（否则 AttributeError 静默吞结果）；语言变体同 design_id 需归并
- **0 下载是真实信号不是 bug**：实测「磁铁推牌」官方 downloadCount=0（冷启动），此前 DDG 启发式把它误排第一——真实数据纠正了启发式误判

## 与其他 Skill 的接口

- 找到模型 → 用户要改尺寸/开孔 → 转交 **bambu-studio-ai**（analyze+parametric 管线）
- 找不到 → 征询用户走生成（Tripo/Meshy，见 bambu-studio-ai/generate.py）
- 多色需求 → 转交 AMS 编排流程（colorize）

## 合规红线

- **轻量优先**：site: 检索 + 官方端点单次轻量增强，不批量抓取、不绕验证码、不存图
- 官方 design-service 端点是**未文档化公开接口**：单次轻调用、不代下载；引用时注明出处链（Bambuddy wiki / Pr0zak/YASTL#51）
- og:image / 详情字段拿不到 → 直接文字卡片，不重试硬闯
- 用户要下载 → 给链接让用户在浏览器/Studio 里自行下载（MakerWorld 下载需登录态，skill 不代抓文件）

## References

- `references/design-service-api.md` — 官方 design-service API 完整档案（端点/字段/解析陷阱/合规出处/验证案例）
- `references/feasibility.md` — 可行性实测报告（降级链每层的数据依据）
- `references/rewrite-patterns.md` — 改写模式库（含 EDC 推牌场景，持续积累）

## 回归场景（任何代码改动后必须重跑）

0.4.0 审计后固化的最小回归集，每条对应一个曾修过的bug类：

| 场景 | 命令 | 验证点 |
|---|---|---|
| 国际站+enrichment | `search_mw.py "phone stand" --source intl --limit 3` | total>0；官方数据补全；`layers[].error` 可见 |
| score/signals字段 | `search_mw.py "SKADIS cable holder" --source auto --limit 4` | 每条结果含 `score`/`signals` 键（死代码回归） |
| 中文站正则 | `search_mw.py "洞洞板 数据线收纳" --source cn --limit 4` | 能命中 `/zh/models/` 及其他语言前缀页 |
| plain模式 | `search_mw.py "mario pegboard" --source plain --limit 4` | 走 `_ddg_plain`（不是cn重复）；layer名为 `ddg_plain` |
| 单模型元数据 | `search_mw.py --meta "https://makerworld.com/en/models/717070-phone-stand"` | 403 优雅降级 `fetched:false` |
| 端到端时延 | `time search_mw.py "phone stand" --source auto --limit 4` | ~24s 全链（并行层15s + join封顶15s内） |

判读要点：DDG限流时某层返回0属环境问题（看 `layers[].error` 是 TimeoutError 即确认），不算脚本回归；但其余层正常时 total 应>0。