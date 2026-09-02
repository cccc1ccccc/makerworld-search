# L1 改写模式库

持续积累的「用户说法 → 检索词组」对照。每次真实使用中发现新的好模式就补进来。

## 已验证模式

| 用户说 | 改写词组 | 实测效果 |
|---|---|---|
| 挂洞洞板的数据线收纳 | SKADIS cable holder / pegboard cable organizer / 洞洞板 数据线 / wall cable clip | 4组20个去重结果，前10全相关 ✅ 2026-09-02 |
| 手机支架 | phone stand | 国际站3个真模型页 ✅ |
| EDC玩具 | EDC fidget / 推牌 解压 / fidget slider push / 指尖玩具 | 14个去重，推牌品类4个精准命中（夹心饼干推牌/Magnetic Push Slider等）；「推牌 解压」组撞限流0结果但其余组兜住 ✅ 2026-09-02 |
| 马里奥×宜家洞洞板配件 | mario skadis / mario pegboard / 马里奥 洞洞板 / super mario pegboard hook | 17个去重，IP×功能双约束有效；第一名「Ikea Skadis Mario NEW DESIGN」官方精选+8,443下载+18,302收藏断层第一 ✅ 2026-09-02 |

## 复合查询改写心法（马里奥案例沉淀）

- **IP×功能双约束**：IP词(马里奥/mario)和平台词(洞洞板/SKADIS/pegboard)必须同组出现，单独搜IP会漂移
- **IP配件是大类**：mario pegboard / mario hook / mario shelf 都有真实爆款，IP×洞洞板是MakerWorld成熟品类
- **警惕标题漂移**：作者改标题后DDG残留旧索引（Kakashi/McLaren混入马里奥结果），L3必须核对标题相符度

## EDC场景改写心法（从实测沉淀）

- EDC是国际站强品类：`EDC fidget`/`fidget slider`/`push slider` 英文词召回远好于中文
- 推牌=push slider/slider，指尖陀螺=spinner，磁推=magnetic push——**品类黑话直译比泛词强**
- 「解压」在中文站是高频tag词，但DDG中文索引不稳定，别单押

## 改写心法（从实测沉淀）

1. **专名 > 通名**：「SKÅDIS/宜家洞洞板」比「洞洞板」召回更准；「3030型材」不要写成「铝型材」
2. **中文站吃中文词，国际站吃英文词**：`--source cn` 配中文词组、`intl` 配英文词组，auto时全出
3. **DDG慢是常态**：三层并行后端到端 ~20s；中文层偶发0结果多为同IP限流（多组词间天然间隔可缓解）。每组词用 `--limit 4` 控制量，别贪多
4. **结果<2个时的升级路径**：换同义词再试一轮 → 仍无 → 建议生成兜底（generate.py）
5. **Printables API字段最全**（封面图/下载数/点赞数都有），但内容偏Prusa生态，作为MakerWorld的补集而非替代

## 待验证场景（遇到后补录）

- [ ] 3030型材相关（型材支架/线槽）
- [ ] 摄影附件（1/4螺口/冷靴/灯架）
- [ ] 修复件（家电断卡扣/铰链/旋钮）
- [ ] 玩具/摆件类（IP词+品类词组合的召回率）