<div align="center">

<img src="docs/banner.svg" width="100%" alt="Pulsar · 照见">

### Pulsar · 照见：为领域研究者而生的自动情报引擎

[English](README.md) / 中文

<a href="https://github.com/sou350121/Pulsar-KenVersion">GitHub</a> · <a href="https://github.com/sou350121/Pulsar-KenVersion/issues">问题反馈</a> · <a href="AGENTS.md">部署文档</a> · <a href="scripts/SCRIPTS.md">Pipeline DAG</a>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![Node](https://img.shields.io/badge/Node-22%2B-green)](https://nodejs.org)
[![Stars](https://img.shields.io/github/stars/sou350121/Pulsar-KenVersion?style=social)](https://github.com/sou350121/Pulsar-KenVersion/stargazers)

👋 加入我们的社区

📡 <a href="https://github.com/sou350121/VLA-Handbook">VLA-Handbook</a> · <a href="https://github.com/sou350121/Agent-Playbook">Agent-Playbook</a> · <a href="https://github.com/sou350121/Pulsar-KenVersion/issues">GitHub Issues</a>

</div>

---

## 项目概览

### 领域情报系统面临的挑战

每一个长期跟踪某个技术领域的研究者，迟早都会遇到这六类问题：

- **信号过载** — arXiv 每天新增 30+ 篇 VLA 论文，没有评分机制就是噪音，逐篇阅读根本不现实
- **推理不透明** — AI 摘要告诉你"这篇很重要"，但不给判断依据，既不能信任，也无法复现
- **知识不沉淀** — 今天读的论文、上周的社区热议，全消失在收件箱和消息流里，一个月后找不到
- **管道不可靠** — cron job 静默失败，不报警，发现时已缺失一周数据，手动补救成本极高
- **判断无从验证** — "AI 趋势预测"没有历史正确率，无法评估信息源的可信度，全靠感觉
- **认知无法更新** — 领域假设写死在脑子里，不随新证据调整，越用越偏离现实

### Pulsar 如何解决

Pulsar 是一个运行在服务器端的领域情报 pipeline。它不替你读东西，而是**把"读什么"这件事自动化**——评分、筛选、推理、存档、自愈、校准，全部自主完成。

- **评分优先，噪音在 LLM 之前截断 → 解决信号过载**：⚡/🔧/📖/❌ 四级评分引擎，30 篇原始论文 → 3–5 篇进入深度推理，节省 80%+ 推理成本
- **三段式可观测推理链 → 推理透明可复现**：`prep → agent → post`，每阶段有明确 I/O，中间产物落盘可检查，失败在哪一段，一眼看出
- **结构化知识写入 Git → 知识永久沉淀**：所有输出写为 Markdown，推送到 GitHub，有 commit 历史，全文 grep，不依赖任何 SaaS
- **Watchdog 自愈系统 → 管道故障自恢复**：15 项健康监控，7 类故障场景自动重跑，日志全程记录，不需要人工介入
- **双周预测 + ✅/❌ 历史追踪 → 判断有据可查**：每两周的报告必须回顾上期预测，正确率有完整记录，信息源可信度用数据说话
- **月度假设校准 → 认知随证据更新**：19 条领域假设，每月自动统计触发率，保守更新置信度，置信度下降的假设自动进入补课队列

---

## 快速上手

### 前置要求

开始之前，请确保你的环境满足以下要求：

- **操作系统**：Linux（推荐）、macOS
- **Python 版本**：3.9 或更高版本
- **Node.js 版本**：22 或更高版本
- **Moltbot**：[https://molt.bot](https://molt.bot)（提供定时任务调度 + 消息发送能力）
- **网络连接**：需要能访问 arXiv、GitHub API、DashScope API

**所需密钥（4 项）**：

| 密钥 | 用途 | 获取方式 |
|------|------|---------|
| DashScope API Key | LLM 调用（qwen3.5-plus） | [阿里云百炼](https://dashscope.aliyun.com) → API Keys |
| GitHub Token | 推送知识到 GitHub 仓库 | GitHub Settings → Developer Settings → Tokens (repo write) |
| Telegram Bot Token | 发送每日情报推送 | Telegram 搜索 @BotFather → /newbot |
| Telegram Chat ID | 推送目标频道 ID | 搜索 @userinfobot，发任意消息即可获取 |

---

### 1. 获取代码

```bash
git clone https://github.com/sou350121/Pulsar-KenVersion ~/clawd
cd ~/clawd
```

> ⚠️ **重要**：所有脚本已预配置为 `~/clawd/` 目录结构。若克隆到其他路径，需执行以下命令更新硬编码路径：
> ```bash
> MYUSER=$(whoami)
> find scripts/ -name "*.py" | xargs sed -i "s|/home/admin|/home/$MYUSER|g"
> ```

---

### 2. 配置密钥

```bash
cp .env.example .env
```

打开 `.env`，填入你的密钥：

```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
TELEGRAM_BOT_TOKEN=xxxxxxxxx:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
MOLTBOT_GATEWAY_PORT=18789
```

> 💡 **提示**：Telegram Chat ID 可以是个人用户 ID（正整数）或频道 ID（负整数）。对于频道，需要先将 Bot 设置为频道管理员。

👇 根据你的使用场景，展开查看详细配置说明：

<details>
<summary><b>DashScope 配置详解（阿里云百炼）</b></summary>

Pulsar 所有 LLM 调用均使用 DashScope，兼容 OpenAI SDK 格式。

1. 前往 [https://dashscope.aliyun.com](https://dashscope.aliyun.com) 注册并开通服务
2. 进入「API Keys」页面，创建一个新 Key
3. 推荐开通模型：`qwen3.5-plus`（质量与速度平衡最佳）

配置完成后，Pulsar 的所有脚本将通过以下端点调用：

```
https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

无需额外代码修改，`.env` 中的 `DASHSCOPE_API_KEY` 即可直接生效。

</details>

<details>
<summary><b>Telegram Bot 配置详解</b></summary>

Pulsar 通过 Moltbot 发送每日情报推送，无需直接调用 Telegram API。

1. 打开 Telegram，搜索 `@BotFather`
2. 发送 `/newbot`，按提示创建 Bot，获取 Token（格式：`123456789:ABCdef...`）
3. 将 Token 填入 `.env` 的 `TELEGRAM_BOT_TOKEN`
4. 获取你的 Chat ID：搜索 `@userinfobot`，发送任意消息，它会返回你的 ID
5. 将 Chat ID 填入 `.env` 的 `TELEGRAM_CHAT_ID`

如果要推送到频道：

```bash
# 先让 Bot 加入频道（设为管理员），然后获取频道 ID：
# 频道 ID 格式为负数，例如 -1001234567890
```

> 💡 **提示**：Pulsar 支持多个 TG 账号（VLA 频道 / AI Agent 频道分开推送）。详见 [AGENTS.md](AGENTS.md)。

</details>

<details>
<summary><b>GitHub Token 配置详解</b></summary>

Pulsar 通过 GitHub Contents API 将每日输出推送到知识库仓库。

1. 前往 GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens
2. 创建新 Token，Repository access 选择你的目标仓库（VLA-Handbook / Agent-Playbook）
3. 权限选择：`Contents: Read and Write`
4. 将 Token 填入 `.env` 的 `GITHUB_TOKEN`

在 `memory/` 目录下创建 GitHub 配置文件（这些文件不在仓库中，需从模板创建）：

```bash
mkdir -p memory
cp config/github-config.template.json memory/github-config-vla-handbook.json
cp config/github-config.template.json memory/github-config-agent-playbook.json
```

然后编辑每个文件，填入你的仓库信息：

```json
{
  "repo": "your-username/VLA-Handbook",
  "api_base": "https://api.github.com",
  "token_env": "GITHUB_TOKEN",
  "branch": "main"
}
```

</details>

---

### 3. 启动 Moltbot 网关

Moltbot 负责调度所有定时任务并发送 Telegram 消息。先安装：

```bash
npm install -g moltbot
```

然后启动网关：

```bash
pkill -f moltbot-gateway || true
nohup moltbot gateway run --bind loopback --port 18789 --force \
  > /tmp/moltbot-gateway.log 2>&1 &
```

验证网关正常运行：

```bash
# 检查端口
ss -ltnp | grep 18789

# 查看网关日志
tail -n 20 /tmp/moltbot-gateway.log
```

预期输出：

```
Gateway running on ws://127.0.0.1:18789
```

---

### 4. 加载定时任务

33 个定时任务已预配置在 `config/jobs.template.json` 中。在启动网关**之前**（或先停止网关），复制到 Moltbot 任务目录：

```bash
pkill -f moltbot-gateway || true
mkdir -p ~/.openclaw/cron
cp config/jobs.template.json ~/.openclaw/cron/jobs.json
```

然后重启网关并验证：

```bash
nohup moltbot gateway run --bind loopback --port 18789 --force \
  > /tmp/moltbot-gateway.log 2>&1 &
moltbot cron list
```

你应该能看到 33 个定时任务，涵盖 VLA 和 AI 两条 pipeline。

---

### 5. 跑第一个 Pipeline

让我们运行一个完整的 VLA 信号收集示例，体验 Pulsar 的核心功能。

#### 收集今日 arXiv VLA 论文

```bash
python3 scripts/vla-rss-collect.py
```

#### 预期输出

```
（无输出 — 脚本成功时静默，不打印任何内容）
```

验证收集结果：

```bash
# 检查今日 RSS 文件是否生成
ls ~/clawd/memory/vla-rss-*.json

# 查看最近 3 篇热点论文
python3 -c "
import json
with open('memory/vla-daily-hotspots.json') as f:
    d = json.load(f)
papers = sorted(d.get('reported_papers', []), key=lambda x: x.get('date',''), reverse=True)[:3]
for p in papers:
    print(p.get('rating','?'), p.get('title',''))
"
```

#### 触发完整评分 + 推送

```bash
# 运行评分 pipeline（会自动推送到 Telegram）
moltbot cron run <vla-hotspots-job-id> --force --timeout 180000 --expect-final
```

> 📝 **注意**：首次运行需要约 3–5 分钟完成 LLM 推理。网关必须处于运行状态。

恭喜！你已成功运行 Pulsar 🎉

---

## 核心概念

### 1. 信号评级引擎

Pulsar 在每次 LLM 调用之前，先用规则引擎对所有原始信号评级，而不是把所有内容都喂给 LLM。

**四级评分体系**：

| 评级 | 含义 | 条件 | 每日上限 |
|------|------|------|---------|
| ⚡ | 突破性进展 | 满足全部 4 项条件（顶级机构 + 关键技术 + 高工程价值 + 强相关） | 1 篇 |
| 🔧 | 工程价值 | 满足 3 项条件 | 5 篇 |
| 📖 | 值得关注 | 满足 2 项条件 | 无限 |
| ❌ | 不相关 | 满足 0–1 项条件 | — |

评分脚本：`scripts/rate-vla-daily.py`。只有 ⚡ 和 🔧 级别的论文才会进入下游 LLM 深度分析，其余直接过滤。

**效果**：每天 28 篇原始论文 → 平均 4–6 篇进入推理，LLM 成本降低约 80%。

---

### 2. 三段式推理链

每一条 pipeline 都遵循相同的三段式结构：

```
prep-*.py          →    run-*-two-phase.py    →    post-*.py
（结构化收集）           （LLM 推理）                （验证 + 输出）
     ↓                        ↓                        ↓
candidates JSON          LLM output JSON           memory + GitHub + TG
```

每阶段的产物都写入 `memory/tmp/` 目录，方便调试：

```bash
ls memory/tmp/
# vla-social-candidates-2026-XX-XX-*.json   ← prep 阶段输出
# vla-social-llm-output-2026-XX-XX-*.json   ← agent 阶段输出
```

如果 pipeline 中途失败，Watchdog 会检测到残留的 `llm-output` 文件并直接从 post 阶段恢复，**跳过重复的收集和 LLM 调用**。

---

### 3. 知识写入 Git

Pulsar 所有有价值的输出都通过 GitHub Contents API 推送到公开仓库：

```
输出类型                →    目标路径
VLA 论文评分             →    VLA-Handbook/theory/...
AI 社交情报             →    Agent-Playbook/memory/blog/archives/ai-social-intel/
AI 每日精选             →    Agent-Playbook/memory/blog/archives/ai-daily-pick/
双周推理报告            →    */reports/biweekly/
双周反思问题            →    */reports/biweekly/reflection_*.md
```

推送脚本：`scripts/gh-contents-upload.py`（支持创建/更新，自动处理 SHA）。

**好处**：
- 全文 grep（`git log -S "flow matching"` 找到所有提到过的内容）
- 永久存档，不依赖 SaaS
- 可以 Fork 知识库，建立自己的领域知识图谱

---

### 4. Watchdog 自愈系统

`scripts/daily-watchdog.py` 每天 10:15 上海时间运行，检查 15 项健康指标：

| 检查项 | 判断标准 | 自愈动作 |
|--------|---------|---------|
| `vla_rss` | 今日 RSS 已收集 | 触发 `vla-rss-collect.py` |
| `vla_hotspots` | 今日 hotspots 已更新 | 触发 hotspots cron job |
| `vla_social` | 今日社交情报有信号 | 触发 social pipeline |
| `vla_release` | Release tracker 今日已检查 | 触发 release tracker |
| `vla_rating` | 评分在 10 小时内完成 | 警告（不自愈） |
| `aiapp_social` | 今日 AI 社交情报 > 0 信号 | 触发 social pipeline |
| `ai_daily_pick` | 今日精选已生成 | 警告 |
| `disk_space` | 磁盘使用 < 85% | 警告；> 95% 报错 |
| ... | ... | ... |

自愈遵循 DAG 顺序（rss → daily → social），避免依赖未就绪的数据。

运行日志：`memory/watchdog-log.json`（保留 60 条，包含 killed / 恢复记录）。

---

### 5. 双周预测 ✅/❌ 闭环

每隔两周，Pulsar 会生成一份推理报告（cron job），包含对未来 2 周的可验证预测：

```markdown
### 预测（2026-XX-XX 到 2026-XX-XX）
1. ⏳ Flow matching 将超过 diffusion policy 成为策略学习主流 —— 验证条件：⚡ 级论文中 flow matching 占比 > 50%
2. ⏳ Unitree G1 SDK 将出现首个第三方社区插件 —— 验证条件：GitHub search 可找到相关 repo
```

下一期报告会回顾这些预测：

```markdown
### 上期预测回顾
1. ✅ 已验证 —— 本期 4/5 篇 ⚡ 论文使用 flow matching（GenPlanner, SafeFlowMatcher...）
2. ❌ 落空 —— 暂未发现第三方插件，G1 社区仍以官方 SDK 为主
```

这个机制让系统的判断准确率有历史记录，可追溯，不靠感觉。

---

### 6. 月度假设校准

系统维护 `memory/assumptions.json`，记录 19 条领域假设，每条带置信度（0–1）：

```json
{
  "id": "V-001",
  "text": "Flow matching 正在替代 diffusion policy 成为 VLA 策略学习主流",
  "confidence": 0.72,
  "last_updated": "2026-02-01"
}
```

每月 28 日，`monthly-calibration-agg.py` 自动：
1. 统计 30 天内各假设的触发率
2. 保守更新置信度（每月 max ±0.08）
3. 置信度持续下降的假设写入 `watch-list.json`

Watch-list 的作用：`prep-calibration-check.py` 会在每日检查时，对 watched 假设自动注入更多相关信号——系统会主动为自己补课，而不需要人工干预。

---

## 项目架构

```
Pulsar-KenVersion/
├── scripts/                    # 55 个 pipeline 脚本
│   ├── prep-*.py               # 数据收集层（RSS、web search、GitHub API）
│   ├── run-*-two-phase.py      # 双阶段执行层（prep + LLM agent）
│   ├── post-*.py               # 后处理层（验证 + 写 memory + GitHub + TG）
│   ├── daily-watchdog.py       # 健康监控 + 自愈（15 项检查）
│   ├── memory-janitor.py       # 定期清理过期文件
│   ├── memory-upsert.py        # 通用 memory 追加写入工具
│   ├── gh-contents-upload.py   # GitHub Contents API 推送
│   ├── _vla_expert.py          # VLA pipeline 共享模块
│   └── SCRIPTS.md              # 完整 pipeline DAG 文档
│
├── config/
│   ├── active-config.template.json  # 研究方向 + 关键词追踪配置模板
│   ├── assumptions.template.json    # 19 条领域假设配置模板
│   ├── github-config.template.json  # GitHub 推送目标配置模板
│   └── jobs.template.json           # 33 个 cron job 配置
│
├── memory/                     # 本地知识存储（.gitignored，自动创建）
│   ├── vla-daily-hotspots.json # VLA 每日热点论文
│   ├── vla-social-intel.json   # VLA 社交情报（90 天）
│   ├── ai-app-social-intel.json# AI 应用社交情报（90 天）
│   ├── assumptions.json        # 19 条领域假设 + 置信度
│   ├── watchdog-log.json       # Watchdog 运行日志
│   ├── tmp/                    # Pipeline 中间产物（60 天自动清理）
│   └── github-config-*.json    # GitHub 推送目标（从 config 模板创建）
│
├── docs/
│   └── banner.svg              # 项目 banner
│
├── AGENTS.md                   # 完整部署指南（供 AI Agent 参考）
├── .env.example                # 密钥模板（复制为 .env 填写）
└── LICENSE                     # MIT
```

---

## 和同类工具的差距

每个工具都有真实的优势，先说清楚：

**选 Feedly AI**：零配置、移动端流畅、100 万+ 信源、团队协作——成熟产品，开箱即用。  
**选 ResearchRabbit**：学术文献综述、2.7 亿篇论文、视觉化引用图谱——系统性学术覆盖很难被超越。  
**选 MineContext**：捕捉你自己读过的内容——完全本地，保护隐私，不需要提前定义监控主题。  
**选 Pulsar**：需要服务器侧自主运行、持续生成结构化知识资产、故障自愈、月度自我校准的 pipeline。

| 维度 | Feedly AI | ResearchRabbit | MineContext | **Pulsar** |
|------|-----------|---------------|-------------|------------|
| **最擅长** | 团队情报订阅、移动端 | 学术引用图谱 | 个人上下文捕捉 | 自主领域情报 pipeline |
| **部署方式** | ☁️ 仅 SaaS | ☁️ 仅 SaaS | ✅ 本地 / 开源 | ✅ 自托管 / 开源 |
| **费用** | \$1,600–3,200 / 月 | 封闭定价 | 免费 | 免费 |
| **配置成本** | ✅ 零配置 | ✅ 零配置 | ✅ 桌面安装 | ⚠️ 约 1 小时 |
| **信号评分** | ❌ | ❌ | ❌ | ✅ ⚡/🔧/📖/❌ LLM 前截断 |
| **推理透明度** | ❌ 黑盒摘要 | ❌ | ❌ | ✅ 三段可观测链路 |
| **故障自愈** | ❌ | ❌ | ❌ | ✅ 7 条自动恢复路径 |
| **信念校准** | ❌ | ❌ | ❌ | ✅ 19 条假设，月度更新 |
| **预测追踪** | ❌ | ❌ | ❌ | ✅ 每两周 ✅/❌ 历史验证 |
| **知识输出** | 订阅流 / 收件箱 | 图谱视图 | 本地摘要 | 结构化 Markdown → Git |
| **硬件需求** | N/A（云端） | N/A（云端） | 桌面应用 | **2 GB RAM VPS** |

---

## 仿生认知架构

Pulsar 的内部分层参考认知有机体设计，而非传统数据管道：

| 认知层 | 生物类比 | Pulsar 组件 |
|--------|---------|------------|
| **感知层** | 感觉器官 | arXiv RSS · GitHub releases · 社区讨论 |
| **过滤层** | 丘脑闸门 | 评分引擎（⚡/🔧/📖/❌）— 噪音在 LLM 前截断 |
| **推理层** | 皮层处理 | 三段式 LLM：prep → agent → post |
| **记忆层** | 海马体编码 | 结构化 Markdown → GitHub |
| **元认知层** | 前额叶反思 | 双周预测回顾 · 月度假设校准 |
| **免疫系统** | 自身免疫 | Watchdog：15 项健康检查，7 条自愈路径 |

---

## 关键数字

| 指标 | 数值 |
|------|------|
| 自动排程任务 | **33** 个 cron job，全自动运行 |
| Pipeline 脚本 | **55** 个，覆盖 VLA 和 AI 两个研究领域 |
| 追踪假设 | **19** 条，月度置信度自动更新 |
| Watchdog 检查 | **15** 项健康指标，**7** 条自愈路径 |
| 端到端延迟 | **< 2 小时**：RSS → 评分完成 → TG 推送 |
| 知识保留 | 社交情报 / hotspots **90 天**滚动 · 报告永久 Git 存档 |
| 硬件需求 | **2 GB RAM**，最低配 VPS 即可运行 |

---

## 输出知识库

Pulsar 每天向以下两个公开仓库输出内容：

| 仓库 | 领域 | 主要内容 |
|------|------|---------|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | 机器人 · VLA 研究 | 每日论文评分 · 理论深度解析 · 双周预测报告 · VLA 社交情报 |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | AI 应用 · Agent 工具 | 工具日报 · 框架架构评审 · AI 社交情报 · 每日精选 |

Fork 这两个仓库，再部署 Pulsar，你就有了一套完整的领域知识积累系统。

---

## 进阶阅读

| 文档 | 内容 |
|------|------|
| [AGENTS.md](AGENTS.md) | 完整部署指南：密钥配置 · 路径说明 · 常见问题 |
| [scripts/SCRIPTS.md](scripts/SCRIPTS.md) | 55 个脚本的完整 DAG 图 · 每个脚本的输入输出 |
| [VLA-Handbook/scripts/](https://github.com/sou350121/VLA-Handbook/tree/main/scripts) | VLA pipeline 示例输出 |
| [Agent-Playbook/reports/biweekly/](https://github.com/sou350121/Agent-Playbook/tree/main/reports/biweekly) | 双周推理报告归档（含预测回顾） |

---

## 社区 & 参与

有问题、有想法、想 Fork 改造成自己领域的版本？

- 💬 **提 Issue**：[GitHub Issues](https://github.com/sou350121/Pulsar-KenVersion/issues)
- 🔀 **Pull Request**：欢迎改进 pipeline、增加新领域支持、修复 bug
- 📡 **查看输出**：[VLA-Handbook](https://github.com/sou350121/VLA-Handbook) · [Agent-Playbook](https://github.com/sou350121/Agent-Playbook)

---

*MIT License — Fork 一份，改成你自己领域的 Pulsar。*

