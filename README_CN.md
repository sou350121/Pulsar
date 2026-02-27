<p align="center"><img src="docs/banner.svg" width="100%" alt="Pulsar · 照见"></p>

# Pulsar · 照见：为领域研究者而生的自动情报引擎

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Lang](https://img.shields.io/badge/README-English-blue)](README.md)

Pulsar 是一个运行在服务器端的领域情报 pipeline，持续监控 AI / VLA 研究生态，通过多阶段 LLM 处理将原始信号提炼为结构化知识资产，并通过月度校准机制不断提升自身判断精度。

由照见系统驱动，2026 年开源。

---

## 它解决的核心问题

构建或维护领域情报系统的工程师，每天面对六类问题：

1. **信号过载** — arXiv 每天 30+ 篇论文，没有评分机制就是噪音，逐篇阅读不现实
2. **推理不透明** — AI 摘要告诉你"这很重要"，但不解释判断依据，无法信任也无法复现
3. **知识不沉淀** — 今天读的论文、明天的社区热议，消失在收件箱和消息流里，一周后找不到
4. **管道不可靠** — cron job 静默失败不报警，发现时已缺失一周数据，补救成本极高
5. **判断无法验证** — "AI 趋势预测"没有历史正确率，无法评估信息源的可信度
6. **认知不会更新** — 领域假设写死不变，不随新证据调整，越用越偏离现实

---

## 六个核心机制

**1. 评分优先，噪音在 LLM 之前截断**  
⚡/🔧/📖/❌ 四级评分引擎，每篇论文在进入 LLM 推理前先被评级。每天 30 篇原始输入 → 精选 3-5 篇进入深度分析，节省 80%+ 推理成本。评分依据：主题相关性 × 机构权重 × 工程可用性。

**2. 三段式可观测推理链**  
`prep（结构化收集）→ agent（LLM 推理）→ post（语义校验 + 结构化输出）`。每阶段有明确的输入输出格式，中间产物落盘可检查。推理过程不是黑盒——失败在哪一段，一眼看出。

**3. 结构化知识写入 Git**  
所有输出写为 Markdown，通过 GitHub Contents API 推送到公开仓库（[VLA-Handbook](https://github.com/sou350121/VLA-Handbook) / [Agent-Playbook](https://github.com/sou350121/Agent-Playbook)）。有完整 commit 历史，全文可 grep，永久可查，不依赖任何 SaaS。

**4. Watchdog 自愈系统**  
`daily-watchdog.py` 持续监控 15 项健康指标。检测到失败后，按 DAG 顺序自动触发重跑（rss → daily → social），7 类故障场景无需人工介入。运行日志写入 `memory/watchdog-log.json`，killed / 恢复全程可查。

**5. 双周预测 + ✅/❌ 历史追踪**  
每两周的推理报告包含可验证预测，下一期必须回来打分：✅ 已验证 / ❌ 落空 / ⏳ 待观察。正确率有完整记录。信息源是否可信，不靠感觉，靠数据。

**6. 月度假设校准**  
系统维护 19 条领域假设，每条带置信度分数（0–1）。每月自动统计 30 天触发率，保守更新置信度（max ±0.08/月）。置信度持续下降的假设进入 watch-list，下一周期自动注入更多相关信号——系统会主动为自己补课。

---

## 和同类工具的差距

每个工具都有真正的优势，先说清楚：

**选 Feedly AI**：零配置、移动端、100 万+信源、团队协作——成熟产品，开箱即用。  
**选 ResearchRabbit**：学术文献综述、2.7 亿篇论文、视觉化引用图谱——系统性覆盖很难被超越。  
**选 MineContext**：捕捉你自己读过的东西——完全本地，保护隐私，不需要提前定义监控主题。  
**选 Pulsar**：需要服务器侧自主运行、持续生成结构化知识资产、故障自愈、月度自我校准的 pipeline。

| 维度 | Feedly AI | ResearchRabbit | MineContext | **Pulsar** |
|------|-----------|---------------|-------------|------------|
| **最擅长** | 团队情报订阅、移动端 | 学术引用图谱 | 个人上下文捕捉 | 自主领域情报 pipeline |
| **部署** | ☁️ 仅 SaaS | ☁️ 仅 SaaS | ✅ 本地 / 开源 | ✅ 自托管 / 开源 |
| **费用** | \$1,600–3,200 / 月 | 封闭定价 | 免费 | 免费 |
| **配置成本** | ✅ 零配置 | ✅ 零配置 | ✅ 桌面安装 | ⚠️ 约 1 小时 |
| **信号评分** | ❌ | ❌ | ❌ | ✅ ⚡/🔧/📖/❌ LLM 前截断 |
| **推理透明度** | ❌ 黑盒摘要 | ❌ | ❌ | ✅ 三段可观测链路 |
| **自愈恢复** | ❌ | ❌ | ❌ | ✅ 7 条自动恢复路径 |
| **信念校准** | ❌ | ❌ | ❌ | ✅ 19 条假设，月度更新 |
| **预测追踪** | ❌ | ❌ | ❌ | ✅ 每两周 ✅/❌ 历史验证 |
| **知识输出** | 订阅流 / 收件箱 | 图谱视图 | 本地摘要 | 结构化 Markdown → Git |
| **硬件需求** | N/A（云端） | N/A（云端） | 桌面应用 | **2 GB VPS** |

---

## 仿生认知架构

Pulsar 的内部分层参考认知有机体设计，而非传统数据管道：

| 认知层 | 生物类比 | Pulsar 组件 |
|--------|---------|------------|
| **感知层** | 感觉器官 | arXiv RSS · GitHub 发布 · 社区讨论 |
| **过滤层** | 丘脑闸门 | 评分引擎（⚡/🔧/📖/❌）— 噪音在 LLM 前截断 |
| **推理层** | 皮层处理 | 三段式 LLM：prep → agent → post |
| **记忆层** | 海马体编码 | 结构化 Markdown → GitHub |
| **元认知层** | 前额叶反思 | 双周预测回顾 · 月度校准 |
| **免疫系统** | 自身免疫 | Watchdog：15 项健康检查，7 条自愈路径 |

---

## 关键数字

| 指标 | 数值 |
|------|------|
| 自动排程任务 | **33** 个 cron job，全自动，无需人工触发 |
| Pipeline 脚本 | **55** 个，覆盖两个研究领域 |
| 追踪假设 | **19** 条，月度置信度自动更新 |
| Watchdog 检查 | **15** 项健康指标，**7** 条自愈路径 |
| 端到端延迟 | **< 2 小时**：RSS → 评分 → TG 推送 |
| 硬件需求 | **2 GB RAM**，最低配 VPS 即可运行 |

---

## 快速部署

**依赖**：Node 22+ · Python 3.9+ · [Moltbot](https://molt.bot) · DashScope API Key · GitHub Token · Telegram Bot Token

\`\`\`bash
git clone https://github.com/sou350121/Pulsar-KenVersion
cp config/.env.example .env           # 填入密钥
moltbot gateway run --bind loopback --port 18789 --force
moltbot cron import config/jobs.template.json
python3 scripts/vla-rss-collect.py    # 测试单条 pipeline
\`\`\`

完整部署文档：[AGENTS.md](AGENTS.md)

---

## 输出知识库

| 仓库 | 领域 | 内容 |
|------|------|------|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | 机器人 · VLA 研究 | 每日评分 · 理论解析 · 双周预测报告 |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | AI 应用 · Agent 工具 | 工具日报 · 框架评审 · 社交情报 |

---

*MIT License — Fork 一份，改成你自己领域的 Pulsar。*
