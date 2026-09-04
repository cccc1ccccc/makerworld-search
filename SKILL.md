---
name: makerworld-search
description: "Natural-language semantic search for 3D printable models via Bambu's official search-service API (no token). Activate when user wants to find/discover 3D models, e.g. 'find me a pegboard cable holder', '找一个手机支架', '找模型'. Pipeline: L1 intent→keyword rewrite (bilingual) → L2 official search API (real relevance ranking + real counts in every hit) → L2b design-service summary fill → L3 result cards with intent gatekeeping."
version: "0.5.0"
license: MIT
keywords:
  - 3d model search
  - makerworld
  - semantic search
  - find models
  - stl search
---

# 🔎 MakerWorld 语义搜索

用户一句话 → L1 语义改写 → L2 官方搜索 API → L2b 简介补全 → L3 结果卡片

**架构原则：全部走官方端点。** 2026-09-05 实测发现 Bambu 官方 search-service 搜索端点（`/v1/search-service/select/design2`，无需 token）——DDG 发现层彻底退役。官方搜索自带相关性排序 + 每条结果的真实下载数/点赞/收藏/封面/tags，中文关键词原生支持，无 Cloudflare 墙、无限流担忧。agent 只负责 L1 意图改写和 L3 意图把关，中间链路全部官方。

---

## Pipeline（每次查询必走）

```
用户需求（自然语言）
   │
   ▼
[L1 语义改写]（agent 自己做，不调脚本）
   - 提取：物体类型 + 关键属性（尺寸/接口/用途/风格）
   - 输出 2-4 组关键词：中文组 + 英文组 + 同义词组
   - 官方搜索的相关性排序很强（BM25+热度信号），关键词质量直接决定结果
   - 例："挂洞洞板的数据线收纳"
     → 优先 "SKÅDIS cable holder"（官方站是英文为主），
       备选 "洞洞板 数据线 收纳"（中文模型收录不少）、"pegboard cable organizer"
   │
   ▼
[L2 官方搜索层] python3 scripts/search_mw.py "关键词" [--source auto|intl|cn|printables] [--order score|downloads|hot|new|boosts]
   - GET api.bambulab.com/v1/search-service/select/design2?keyword=...&limit=...
   - 无需 token。每条 hit 自带真实下载数/点赞/收藏/打印数 + 封面 + tags + 官方精选标记
   - 默认 orderBy=score（官方相关性算法），可选 hot/downloads/likes/new/boosts
   - 单查询 ~0.6s（对比 v2 DDG 三层并行 ~20s）
   - 多组关键词由 agent 多次调用脚本（每次一组），结果由 agent 合并去重
   │
   ▼
[L2b 简介补全]（脚本内置，自动执行）
   - 对 top-N 结果调 design-service API（/v1/design-service/design/{id}）补 summary
   - ⚠️ 只补 desc，不覆盖 title（design-service 的 titleTranslated 会把中文模型
     机翻成英文，「GAME BOY EDC 磁力推牌」→"GAME BOY EDC Magnetic Pusher"，踩过）
   │
   ▼
[L3 结果卡片]（agent 自己做，不调脚本）
   - 官方相关性排序为候选池，按意图挑 top 3-5
   - 输出卡片：标题（原语言） / 真实下载·赞·藏数 / 封面 / 链接 / 匹配理由
   - 附加：问用户"看中哪个？我可以直接下载→改尺寸→上色"
```

## Quick Reference

| 想做什么 | 命令 |
|---|---|
| 单组关键词搜索 | `python3 scripts/search_mw.py "phone stand" --limit 6` |
| 按下载量排序 | `python3 scripts/search_mw.py "phone stand" --order downloads` |
| 按热度/最新排序 | `--order hot` / `--order new` / `--order boosts` |
| 只查国际站（跳过Printables层） | `python3 scripts/search_mw.py "手机支架" --source intl` |
| Printables 补充层 | `python3 scripts/search_mw.py "cable clip" --source printables` |
| 从 URL 提官方元数据 | `python3 scripts/search_mw.py --meta "https://makerworld.com/en/models/717070-phone-stand"` |

## L1 改写协议（agent 必读）

改写时遵循的规则，按优先级：

1. **物体类型放最前**：支架/收纳/钩子/外壳/玩具 → 类别词是检索主干
2. **接口/标准件用专名**：SKÅDIS(不用"洞洞板")、M3、2020/3030型材、VESA、GoPro、USB-C
3. **中英各搜一组**：官方搜索对中文关键词原生支持（"推牌"直接命中中文模型），但国际站英文模型占多数，双语都查覆盖最全
4. **同义词兜底**：holder/clip/organizer/mount/stand 常互换，结果<3个时换1-2个变体重查
5. **别堆砌**：每组关键词 ≤4 个词；官方相关性算法对长串堆砌词同样失焦

典型改写示例（存入脑内，遇到类似需求直接套）：

| 用户说 | 改写为 |
|---|---|
| 挂洞洞板的数据线收纳 | SKÅDIS cable holder / 洞洞板 数据线 收纳 |
| 打印机旁放耗材的小架子 | AMS filament holder / spool holder |
| 摄影灯的1/4接口底座 | camera 1/4 mount / light mount tripod |
| 遥控器收纳 | remote holder / remote control organizer |
| 隐藏在桌下的走线 | under desk cable management / desk cable clip |

更多实测改写模式（含 EDC 推牌场景）见 `references/rewrite-patterns.md`。

## Implementation Notes (from real tests, 2026-09-05)

- **官方搜索就是相关性排名本身**：`orderBy=score`（默认）= Bambu 自己的排序算法。实测「monster hunter keychain」第一名即精准命中（Palico 钥匙扣，官方精选），v2 时代 DDG 混入的高 pagerank 跑题引流模型不复存在
- **中文原生支持**："推牌"→1706 个总匹配，前列全中文标题；"手机支架"混排中英结果。不再需要"中文站单独一层"
- **title 用 `title` 字段（原语言），别用 `titleTranslated`**：后者是机翻英文，中文模型会丢原名。`title_translated` 字段保留在结果里供 agent 参考
- **搜索 hit 不含 summary/desc**：desc 由 L2b design-service 补全（top-N 限量调用，非批量抓取）
- **`--source intl/cn` 现在只影响是否加 Printables 补充层**：官方搜索 API 不分站（.com 国际站 ID 空间），cn/intl/international 结果一致
- **.cn 站独立 ID 空间的坑仍在**：`--meta` 对 makerworld.com.cn URL 会直接报错提示（design-service API 只认国际站 ID）。搜索结果 URL 统一生成 makerworld.com 域名，天然避开此坑
- **Printables 层（auto 模式）墙内不可达**：8s 超时快速失败，不影响主流程。境外网络可达时作为跨站补充

## L3 卡片格式（输出给用户前先过一遍）

```
🔍 为你找到 N 个模型（官方搜索，按相关性排序）：

1. **GAME BOY EDC 磁力推牌** ｜ MakerWorld
   📥 3199 下载 · 👍 3062 赞 · 封面: [URL]
   简介：磁力推牌，GAME BOY 造型……
   链接：https://makerworld.com/en/models/732713
   匹配：正是你要的"推牌"，tags: EDC/推牌/磁力

2. ...
```

- 每条必含：标题（**原语言**）、链接、真实数据（downloads/likes/collections/staff_pick/prints）、desc 一句话、一句话匹配理由
- **字段都在顶层**（v3 简化）：`r["downloads"]` / `r["likes"]` / `r["collections"]` / `r["staff_pick"]` / `r["cover"]` / `r["tags"]` / `r["desc"]` / `r["title_translated"]`。无 official 嵌套对象
- **数字显示用 `isinstance(n, int)` 判断**，0 下载是真实信号（冷启动模型），不要显示成 '?'
- **staff_pick 是金信号**：`r["staff_pick"]=true` 优先推荐（官方人工精选背书）
- **排序规则**：脚本默认返回官方相关性顺序（score）。agent 可选 `--order downloads` 拿纯热度序。最终输出前逐条判断「标题/简介/tags 与意图的相符度」，不符的剔除或排末位
- 结果 <2 个时：换同义词重查（`holder↔clip↔organizer`）；仍无 → 建议走生成兜底（generate.py）
- 匹配理由必须基于标题/desc/官方 tags 推断，不许编造

## 与其他 Skill 的接口

- 找到模型 → 用户要改尺寸/开孔 → 转交 **bambu-studio-ai**（analyze+parametric 管线）
- 找不到 → 征询用户走生成（Tripo/Meshy，见 bambu-studio-ai/generate.py）
- 多色需求 → 转交 AMS 编排流程（colorize）

## 合规红线

- **轻量优先**：单关键词单次官方搜索 + top-N 简介补全（≤limit 次 design-service 调用），不批量抓取、不绕验证码、不存图
- search-service 与 design-service 均为**未文档化公开接口**（同一 `v1/*-service` 微服务族，纯 GET 无鉴权）：逆向模式出处 Bambuddy wiki（上游 Pr0zak/YASTL#51）+ Doridian/OpenBambuAPI cloud-http.md（Search Service 端点表）。引用时注明出处链
- 用户要下载 → 给链接让用户在浏览器/Studio 里自行下载（MakerWorld 下载需登录态，skill 不代抓文件）

## References

- `references/design-service-api.md` — 官方端点档案（design-service 字段 + search-service 搜索参数/orderBy/实测案例/解析陷阱/合规出处）
- `references/rewrite-patterns.md` — 改写模式库（含 EDC 推牌场景，持续积累）

## 回归场景（任何代码改动后必须重跑）

| 场景 | 命令 | 验证点 |
|---|---|---|
| 英文相关性 | `search_mw.py "phone stand" --limit 4` | total>0；官方计数齐；title 原语言 |
| 中文关键词 | `search_mw.py "推牌" --limit 4` | 中文标题不被机翻覆盖 |
| 排序参数 | `search_mw.py "phone stand" --order downloads --limit 3` | dl 降序 |
| --meta 国际站 | `search_mw.py --meta ".../models/717070-phone-stand"` | fetched:true，官方字段齐 |
| --meta .cn 站 | `search_mw.py --meta ".../models/1270816"` (makerworld.com.cn) | 报独立 ID 空间错误，不返回错配数据 |
| 端到端时延 | `time search_mw.py "phone stand" --source intl` | ~2s（官方搜索 0.6s + 补全） |