# MakerWorld 自然语言搜索 — 可行性调研报告
调研日期: 2026-09-02 | 方法: 实测(非二手资料)

## 核心结论: 可行,但不是"调官方API"的可行,而是"混合管线"的可行

**可行性评级: ★★★☆☆ (有条件可行 — 需采用降级链架构)**

---

## 一、实测发现(一手数据)

### 1. 官方无公开API — 确认
- BambuStudio 源码(217MB全量扫描)确认: Studio 内置的 MakerWorld 面板是**嵌入式WebView**(Next.js前端), 不是原生API调用
- `makerhub-*.bambulab.net` / `makerhub-dev.bambulab-lab.com` 是内部 dev/qa/pre 环境, 公网不可访问
- 官方后端用 graphql (WebViewDialog.cpp 中发现 `wiki.bambulab.com/graphql`), 但端点需认证, 未公开

### 2. Cloudflare 防护 — 真实且概率性拦截
- 直接 curl/requests: 首页 403, 详情页**概率性 200**(同会话先后 403/200, 4连测全403)
- 浏览器栈: Cloudflare 质询页 ("Just a moment..." + 复选框), 无代理的 stealth 浏览器被识别
- Automatio 软文确认: "data center proxies are frequently flagged" — 数据中心IP会被持续标记
- **含义**: 任何"纯抓取"方案在 skill 里都不可靠, 必须有降级链

### 3. 搜索引擎路线 — 已验证可用 (基线)
- `ddgs` (DuckDuckGo) `site:makerworld.com` 搜索实测:
  - 英文: 返回具体模型 URL+标题 (如 `models/717070-phone-stand`)
  - **中文站 `site:makerworld.com.cn` 同样收录** (手机支架→多个具体模型)
  - DDG 对中文查询工作正常
- 但只有 URL+标题, 无封面图/下载数/评分, 无语义理解

### 4. Next.js `_next/data` 端点 — 存在但 buildId 会过期
- JoyCas1no/makerworld-to-wp 用 `makerworld.com/_next/data/<buildId>/ru/3d-models.json` 拿到 designs 列表
- buildId 硬编码会失效, 需动态提取(首页HTML中的 buildId), 且同样受 Cloudflare 管
- 诺文: 该仓库2024年的做法, 现在的站仍是 Next.js, 端点模式依然成立

### 4.5 语义理解层 — 这是 skill 的真正创新点, 且完全可行
- DDG 只有关键词匹配。用户说"我要个能挂洞洞板的数据线收纳", DDG 搜不到(没这个词条)
- 但 agent 本身就是 LLM: **query改写层**(意图→多组关键词/英文中文双语改写)是纯 LLM 能力, 零外部依赖
- 展示层: og:image 可从 DDG 结果的图片结果获取, 或用 preview.py 渲染本地 STL 渲染图
- 这层是全生态 0 竞品: 检索过的所有 bambu/makerworld skill(9个控制类+parametric类)无一做语义检索

### 5. 下载链路 — 有现成方案
- bambu-studio-ai 的 generate.py download 路径 + MakerWorld 模型页有"Open in Bambu Studio"按钮
- MakerWorld 模型 URL 格式: `makerworld.com/en/models/<id>-<slug>`
- 用户端真实场景: 找到模型→生成 3MF 打开到 BS → 打印 — 与方向①"改模型"无缝衔接

### 6. 竞品格局 — 搜索方向 0 竞品
- ClawHub 搜 "makerworld": 无相关 skill (只有 bambu 打印控制类)
- GitHub makerworld 相关仓库: 只有 makerworld-to-wp (WP 导入用, 非搜索)
- **"自然语言搜索"赛道完全无人做**

## 二、架构建议 — 三层降级链 (应对 Cloudflare 概率性拦截)

```
用户自然语言 → [L1 语义层] agent 改写为 2-4 组关键词(中英双语+同义词)
                ↓
            [L2 检索层] 逐组尝试, 按优先级降级:
                ① makerworld.com.cn(中文站) site搜索 — 中文站 CF 管理可能更松(实测DDG收录好)
                ② makerworld.com site搜索 (英文改写)
                ③ _next/data 端点 (动态 buildId) — 若CF放行, 拿全字段(designs数组: 标题/下载/评分/封面)
                ④ 降级到 Printables/Thingiverse/Thangs (printables 有官方API! printables.com/api)
                ⑤ 兜底: 只给 URL 列表, 用户点开看
                ↓
            [L3 展示层] 4-6 个卡片: 标题+链接+来源站+匹配度说明
                       og:image 失败→不放图, 放文字卡片
                       找到后可直接接 generate.py download / 3MF 流程
```

**关键工程决策:**
1. **不硬刚 Cloudflare**: 爬虫方案在 skill 里不可靠。设计上就是降级链, 每层失败下探
2. **⚠️ Printables API 在本机被网络封锁（2026-09-02 探测更正）**: 最初本文写"Printables有官方API可拿全字段"——事实正确但**本机不可达**（api.printables.com 与 www.printables.com 直连 Errno 101，本地三个代理口全 000）。printables_api 层返回 0 的真因是网络，不是 GraphQL schema 漂移。排查顺序：先 curl 探可达性，再疑 schema。VPN 开启后此层可能恢复，代码保留
3. **语义层是差异化核心**: 别人做"搜索"是关键词, 你做的是"意图理解+查询改写+结果筛选"。agent 天然干这个
4. **合规提醒**: 官方无公开API意味着抓取违反 ToS 风险。给 skill 设计"轻量模式"(只搜不抓详情, 用户点链接自己看) 和"富模式"(尝试拿元数据, 失败降级) 两档。活动评审角度: 建议演示以轻量模式为主, 规避官方负面观感

## 三、与方向①②③的关系 — 定位

- **与①的关系**: 搜索是①的"入口": 用户"想要一个 X" → 没有现成模型 → 搜 → 找到 → (可能差5mm) → 接①的改模型闭环
- **与②的关系**: 独立。②是"打印失败归因", 完全不同域
- **与③的关系**: 搜索是③的对偶: ③是"生成", 搜索是"检索"。搜不到的才生成。搜索优先, 生成兜底
- **建议**: 做成 **Skill C**, 与①②并列。但发布内容上, "搜索"演示效果弱于"改模型"和"照片诊断"(无前后对比), 建议作为①的配套模块发布, 不单独发笔记
- **开发量**: 1-2周。核心是 query 改写规则 + 降级链脚本 + 结果卡片化展示。无需 CV, 无 API key

## 四、风险清单

| 风险 | 概率 | 缓解 |
|---|---|--- makerworld.com 被 CF 全量拦截升级 | 中 | 降级链 ④⑤ 兜底; 中文站 + DDG 双源 |
| DDG 对中文站收录不稳定 | 低 | 实测收录好; 且 DDG 支持中文查询 |
| 官方后续开放API | 低(利好) | 端点不变直接接入, 架构不返工 |
| ToS 风险 | 中 | 轻量模式为主; 不存图, 不批量抓, 尊重 robots |
| 演示效果弱 | 中 | 与①绑定演示: "找不到的→生成→改" 全链路故事 |