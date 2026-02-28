<div align="center">

<img src="docs/banner.svg" width="100%" alt="Pulsar · 照见">

### Pulsar · 照见：为领域研究者而生的自动情报引擎

[English](README.md) / 中文

<a href="https://github.com/sou350121/Pulsar">GitHub</a> · <a href="https://github.com/sou350121/Pulsar/issues">问题反馈</a> · <a href="AGENTS.md">部署文档</a> · <a href="scripts/SCRIPTS.md">Pipeline DAG</a>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![Node](https://img.shields.io/badge/Node-22%2B-green)](https://nodejs.org)
[![Stars](https://img.shields.io/github/stars/sou350121/Pulsar?style=social)](https://github.com/sou350121/Pulsar/stargazers)

👋 加入我们的社区

📡 <a href="https://github.com/sou350121/VLA-Handbook">VLA-Handbook</a> · <a href="https://github.com/sou350121/Agent-Playbook">Agent-Playbook</a> · <a href="https://github.com/sou350121/Pulsar/issues">GitHub Issues</a>

</div>

---

## 项目概览

### 领域情报系统面临的挑战

每一个长期跟踪某个技术领域的研究者，迟早都会遇到这六类问题：

- **信号过载** — 每天几十篇新论文/文章，没有评分机制就是噪音，逐篇阅读根本不现实
- **推理不透明** — AI 摘要告诉你"这篇很重要"，但不给判断依据，既不能信任，也无法复现
- **知识不沉淀** — 今天读的内容、上周的社区热议，全消失在收件箱和消息流里
- **管道不可靠** — cron job 静默失败，不报警，发现时已缺失一周数据
- **判断无从验证** — "AI 趋势预测"没有历史正确率，无法评估信息源的可信度
- **认知无法更新** — 领域假设写死在脑子里，不随新证据调整，越用越偏离现实

### Pulsar 如何解决

Pulsar 是一个运行在服务器端的领域情报 pipeline。**你定义领域，Pulsar 运转引擎。** 配置好你的 RSS 源、关键词和 LLM 提供商，评分、筛选、推理、存档、自愈、校准，全部自主完成。

- **评分优先，噪音在 LLM 之前截断 → 解决信号过载**：⚡/🔧/📖/❌ 四级评分引擎，原始信号 → 3–5 条进入深度推理，节省 80%+ 推理成本
- **三段式可观测推理链 → 推理透明可复现**：`prep → agent → post`，每阶段有明确 I/O，中间产物落盘可检查
- **结构化知识写入 Git → 知识永久沉淀**：所有输出写为 Markdown，推送到 GitHub，有 commit 历史，全文 grep，不依赖任何 SaaS
- **Watchdog 自愈系统 → 管道故障自恢复**：15 项健康监控，7 类故障场景自动重跑，日志全程记录
- **双周预测 + 强制 ✅/❌ 评分 → 预测正确率有历史记录**：每份推理报告必须包含带验证条件的可证伪预测，下一期报告必须逐条评分 ✅/❌。准确率永久写入 Git——系统无法悄悄修改过去的判断
- **自我进化的信念系统 → pipeline 主动发现并修正自己的盲区**：系统维护显式的领域假设 × 置信度（0–1）。每月自动识别哪些判断正在被数据验证、哪些在漂移——漂移的假设进入 watch-list，下个周期自动注入更多相关信号，系统主动补课，无需人工介入。与双周 ✅/❌ 评分共同构成完整的自我纠错闭环

---

<details>
<summary><b>🚀 快速上手（点击展开）</b></summary>

## 快速上手

### ⚡ 一键安装（推荐）

克隆仓库后运行引导式安装脚本——自动处理 Python 版本检查、`mcp` 安装、配置文件写入，并打印 Claude Desktop JSON 配置块：

```bash
git clone https://github.com/sou350121/Pulsar ~/clawd
bash ~/clawd/scripts/setup.sh
```

脚本会依次询问：LLM API Key、GitHub Token、Telegram Bot Token + Chat ID、研究域名称与关键词。所有配置文件自动生成。

**非交互 / CI 模式：**
```bash
bash ~/clawd/scripts/setup.sh --non-interactive --memory-dir /path/to/memory
```

> **说明：** `setup.sh` 需要 Python 3.10+，会自动安装 `mcp` 包。如需手动配置，请继续参考下方步骤。

---


### 🤖 AI 辅助配置（Cursor · Claude · ChatGPT）

把以下 prompt 粘贴给任意 AI 编程助手，让它引导你完成交互式配置：

```
我已经克隆了 Pulsar（https://github.com/sou350121/Pulsar）——一个自动化领域情报 pipeline。
请帮我配置为我的研究领域。

请先读取以下文件：
- AGENTS.md                           — 经验证的部署指南
- config/active-config.template.json  — 领域配置模板（RSS 源、关键词、假设）
- config/github-config.template.json  — GitHub 推送目标配置
- .env.example                        — 所需 API 密钥说明

然后帮我完成以下步骤：

1. 配置我的领域（memory/active-config.json）：
   - 我的研究领域：[描述你的领域，例如「生物医学 AI」「气候政策」「金融科技」]
   - 要监控的 RSS 源：[列出你的 feed，或请你根据领域推荐]
   - 需要优先关注的机构/组织：[例如「NIH」「Fed」「OpenAI」]
   - 3–5 条我想每月追踪和校准的领域假设

2. 配置 .env：
   - LLM 提供商：[OpenAI / DeepSeek / Moonshot / DashScope / Groq / 自托管]
   - 我准备好后会提供 API Key

3. 配置 GitHub 推送目标（memory/github-config-primary.json）：
   - 我的知识库仓库：[your-username/your-repo]

4. 如果我不是克隆到 ~/clawd/，更新路径引用：
   MYUSER=$(whoami)
   find scripts/ -name "*.py" | xargs sed -i "s|/home/admin|/home/$MYUSER|g"

5. 运行第一个 pipeline 步骤验证配置。

读完配置文件后，请主动向我提问，帮我填写所有需要自定义的内容。
```

---

### 前置要求

- **操作系统**：Linux（推荐）、macOS
- **Python 版本**：3.9 或更高
- **Node.js 版本**：22 或更高
- **Moltbot**：[https://molt.bot](https://molt.bot)（提供定时任务调度 + 消息发送能力）
- **网络连接**：能访问你配置的 RSS 源、GitHub API 和你选择的 LLM 提供商

**所需密钥**：

| 密钥 | 用途 | 支持的提供商 |
|------|------|------------|
| LLM API Key | 所有推理调用（评分、推理、情报生成） | 任何 OpenAI 兼容端点 — OpenAI、DeepSeek、Moonshot、DashScope（阿里云）、Groq 等 |
| GitHub Token | 推送知识到你的 GitHub 仓库 | GitHub Settings → Developer Settings → Fine-grained tokens |
| Telegram Bot Token | 发送每日情报推送 | Telegram 搜索 @BotFather → /newbot |
| Telegram Chat ID | 推送目标频道 ID | 搜索 @userinfobot，发任意消息即可获取 |
| Tophub API Key *（可选）* | 热门科技资讯源 | [tophubdata.com](https://www.tophubdata.com/) |

---

### 1. 获取代码

```bash
git clone https://github.com/sou350121/Pulsar ~/clawd
cd ~/clawd
```

> ⚠️ **重要**：所有脚本已预配置为 `~/clawd/` 目录结构。若克隆到其他路径，需执行以下命令更新硬编码路径：
> ```bash
> MYUSER=$(whoami)
> find scripts/ -name "*.py" | xargs sed -i "s|/home/admin|/home/$MYUSER|g"
> ```

---

### 2. 配置你的研究领域

从模板复制配置文件并编辑：

```bash
mkdir -p memory
cp config/active-config.template.json memory/active-config.json
```

打开 `memory/active-config.json`，定义：

- **RSS 源** — 任何 Atom/RSS URL：arXiv 分类 feed、博客 feed、GitHub release feed、新闻网站，任何有 feed 的来源
- **关键词** — 标记信号与你的领域相关的词（评分引擎用来过滤噪音）
- **机构标签** — 评分优先级标签（例如 `"[MIT]"`、`"[Google DeepMind]"`、`"[YCombinator]"`）
- **假设** — 你想每月追踪和校准的领域判断

内置的参考配置追踪 **VLA 机器人**（arXiv `cs.RO`、`cs.AI`）和 **AI 开发工具**（科技资讯 feed）。Pipeline 逻辑完全与领域无关——换一套配置，就可以追踪金融科技、生物医学、气候政策或任何其他领域。

同时配置你的 GitHub 知识库推送目标：

```bash
cp config/github-config.template.json memory/github-config-primary.json
# 编辑：将 "repo" 改为你的知识库仓库名（例如 "your-username/your-domain-handbook"）
```

---

### 3. 配置环境变量

```bash
cp .env.example .env
```

打开 `.env`，填入你的密钥：

```env
# LLM 提供商密钥 — 任何 OpenAI 兼容端点均可（见下方详细说明）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx

GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
TELEGRAM_BOT_TOKEN=xxxxxxxxx:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
MOLTBOT_GATEWAY_PORT=18789
TOPHUB_API_KEY=your_tophubdata_api_key   # 可选：热门科技资讯源
```

> 💡 **提示**：Telegram Chat ID 可以是个人用户 ID（正整数）或频道 ID（负整数）。对于频道，需先将 Bot 设置为频道管理员。

👇 根据你的使用场景，展开查看详细配置说明：

<details>
<summary><b>LLM 提供商 — 任何 OpenAI 兼容 API 均可使用</b></summary>

Pulsar 所有 LLM 调用均使用 OpenAI SDK 格式，因此任何兼容提供商都可以直接使用，无需修改 pipeline 逻辑。参考部署使用 **DashScope + qwen3.5-plus**，但你可以切换到任意提供商：

| 提供商 | Base URL | 示例模型 |
|--------|----------|---------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| DashScope（阿里云） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.5-plus` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.1-8b-instant` |
| 自托管 | 你的端点 | Ollama、vLLM、llama.cpp 等 |

**切换提供商方式**：将你的提供商 API Key 填入 `DASHSCOPE_API_KEY`（或重命名该变量），然后在 `scripts/_vla_expert.py` 中更新 base URL 常量——只需改一行。

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

> 💡 **提示**：Pulsar 支持多个 TG 账号（例如不同领域使用不同频道）。详见 [AGENTS.md](AGENTS.md)。

</details>

<details>
<summary><b>GitHub Token 配置详解</b></summary>

Pulsar 通过 GitHub Contents API 将每日输出推送到知识库仓库。

1. 前往 GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens
2. 创建新 Token，Repository access 选择你的目标仓库
3. 权限选择：`Contents: Read and Write`
4. 将 Token 填入 `.env` 的 `GITHUB_TOKEN`

在 `memory/` 目录下创建 GitHub 配置文件（这些文件不在仓库中，需从模板创建）：

```bash
mkdir -p memory
cp config/github-config.template.json memory/github-config-primary.json
```

然后编辑，填入你的仓库信息：

```json
{
  "repo": "your-username/your-domain-handbook",
  "api_base": "https://api.github.com",
  "token_env": "GITHUB_TOKEN",
  "branch": "main"
}
```

</details>

---

### 4. 启动 Moltbot 网关

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
ss -ltnp | grep 18789
tail -n 20 /tmp/moltbot-gateway.log
```

预期输出：

```
Gateway running on ws://127.0.0.1:18789
```

---

### 5. 加载定时任务

定时任务已预配置在 `config/jobs.template.json` 中。在启动网关**之前**（或先停止网关），复制到 Moltbot 任务目录：

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

---

### 6. 跑第一个 Pipeline

内置的参考配置追踪 VLA 机器人 + AI 开发工具两个领域。以下是验证端到端流程的方法：

#### 收集今日信号（VLA 示例）

```bash
python3 scripts/vla-rss-collect.py
```

验证收集结果：

```bash
ls ~/clawd/memory/vla-rss-*.json

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
moltbot cron run <vla-hotspots-job-id> --force --timeout 180000 --expect-final
```

> 📝 **适配你自己的领域**：参考脚本命名为 `vla-*` 和 `ai-app-*`。要追踪其他领域，更新 `memory/active-config.json` 中的 RSS 源和关键词，然后 fork 并重命名相关脚本即可。三段式结构（`prep → run → post`）保持不变。

恭喜！你已成功运行 Pulsar 🎉

---

</details>

## 核心概念

### 1. 信号评级引擎

Pulsar 在每次 LLM 调用之前，先用规则引擎对所有原始信号评级，而不是把所有内容都喂给 LLM。

**四级评分体系**：

| 评级 | 含义 | 条件 | 每日上限 |
|------|------|------|---------|
| ⚡ | 突破性进展 | 满足全部 4 项条件（顶级机构 + 关键技术 + 高工程价值 + 强相关） | 1 |
| 🔧 | 工程价值 | 满足 3 项条件 | 5 |
| 📖 | 值得关注 | 满足 2 项条件 | 无限 |
| ❌ | 不相关 | 满足 0–1 项条件 | — |

评分条件（关键词、机构标签、相关性规则）**全部在你的 `memory/active-config.json` 中定义**，适配新领域无需改动代码。

只有 ⚡ 和 🔧 级别的信号才会进入下游 LLM 深度分析，其余直接过滤。

**效果**：每天几十条原始信号 → 平均 4–6 条进入推理，LLM 成本降低约 80%。

---

### 2. 三段式推理链

每一条 pipeline 都遵循相同的三段式结构：

```
prep-*.py          →    run-*-two-phase.py    →    post-*.py
（结构化收集）           （LLM 推理）                （验证 + 输出）
     ↓                        ↓                        ↓
candidates JSON          LLM output JSON           memory + GitHub + TG
```

每阶段的产物都写入 `memory/tmp/` 目录，方便调试。如果 pipeline 中途失败，Watchdog 会检测到残留的 `llm-output` 文件并直接从 post 阶段恢复，**跳过重复的收集和 LLM 调用**。

---

### 3. 知识写入 Git

所有有价值的输出都通过 GitHub Contents API 推送到你配置的仓库：

```
输出类型                →    目标路径（在 memory/github-config-*.json 中配置）
领域信号评分            →    your-repo/knowledge/ratings/
社交情报                →    your-repo/memory/blog/archives/social-intel/
每日精选                →    your-repo/memory/blog/archives/daily-pick/
双周推理报告            →    your-repo/reports/biweekly/
```

推送脚本：`scripts/gh-contents-upload.py`（支持创建/更新，自动处理 SHA）。

**好处**：
- 全文 grep（`git log -S "你的关键词"` 找到所有历史记录）
- 永久存档，不依赖 SaaS
- Fork 知识库，建立自己的领域知识图谱

---

### 4. Watchdog 自愈系统

`scripts/daily-watchdog.py` 每天运行，检查 15 项健康指标：

| 检查项 | 判断标准 | 自愈动作 |
|--------|---------|---------|
| `rss` | 今日 RSS 已收集 | 触发 RSS 收集脚本 |
| `hotspots` | 今日 hotspots 已更新 | 触发 hotspots cron job |
| `social` | 今日社交情报有信号 | 触发 social pipeline |
| `release` | Release tracker 今日已检查 | 触发 release tracker |
| `rating` | 评分在 10 小时内完成 | 警告（不自愈） |
| `disk_space` | 磁盘使用 < 85% | 警告；> 95% 报错 |
| ... | ... | ... |

自愈遵循 DAG 顺序（rss → daily → social），避免依赖未就绪的数据。

运行日志：`memory/watchdog-log.json`（保留 60 条，包含 killed / 恢复记录）。

---

### 5. 双周预测 ✅/❌ 闭环

每隔两周，Pulsar 会生成一份包含可验证预测的推理报告：

```markdown
### 预测（未来 2 周）
1. ⏳ [你的假设] —— 验证条件：[具体可测量的指标]
2. ⏳ [另一个假设] —— 验证条件：[如果成真，你会观察到什么]
```

下一期报告会回顾这些预测：

```markdown
### 上期预测回顾
1. ✅ 已验证 —— [发现的证据]
2. ❌ 落空 —— [反证]
```

这个机制让系统的判断准确率有历史记录，可追溯，不靠感觉。

---

### 6. 自我进化的信念系统

这是 Pulsar 最核心的创新，也是它与静态 pipeline 最本质的区别。

大多数情报系统只是收集、摘要、然后遗忘。Pulsar 不同——它维护一个**对自身判断的显式模型**，持续追踪这些判断的准确率，并根据证据主动修正它们。

系统在 `memory/assumptions.json` 中记录领域假设，每条带置信度（0–1）：

```json
{
  "id": "V-001",
  "text": "你的领域假设",
  "confidence": 0.72,
  "last_updated": "2026-02-01"
}
```

**自我纠错闭环：**

```
  每日信号
     │
     ▼
  校准检查 ─── 每条信号与假设逐一匹配
     │
     │（每月 28 日）
     ▼
  计算每条假设的触发率
     │
     ├── 数据持续支持 ──▶ 置信度 ▲（max +0.08）
     │
     └── 触发率低 / 漂移 ──▶ 置信度 ▼
                                  │
                                  ▼
                            进入 Watch-list
                                  │
                                  ▼
                         下个周期：信号增强
                         （从 RSS / 社交情报
                          自动注入更多相关信号）
                                  │
                                  ▼
                         更多证据 → 重新评估
                                  │
                                  └──▶ 循环继续

  双周预测 ──▶ ✅/❌ 评分 ──▶ 准确率历史写入 Git
```

**为什么这是自我进化，而不只是自动化：**

- 系统决定**主动去找什么**，而不只是被动收集更多
- 置信度下降不只是一个数字，而是触发主动调查的信号
- 双周 ✅/❌ 评分是对系统推理质量的独立校验
- 假设的置信度变化永久写入 Git——信念的演变有迹可查，不会悄然发生
- Watch-list 不由人工维护，它从数据本身涌现出来

这个闭环持续运行。经过足够多的周期后，系统的置信度分布将反映真实积累的经验证据，而不再是你最初设定的先验。

---

## 项目架构

```
Pulsar/
├── scripts/                    # Pipeline 脚本
│   ├── prep-*.py               # 数据收集层（RSS、web search、GitHub API）
│   ├── run-*-two-phase.py      # 双阶段执行层（prep + LLM agent）
│   ├── post-*.py               # 后处理层（验证 + 写 memory + GitHub + TG）
│   ├── daily-watchdog.py       # 健康监控 + 自愈（15 项检查）
│   ├── memory-janitor.py       # 定期清理过期文件
│   ├── memory-upsert.py        # 通用 memory 追加写入工具
│   ├── gh-contents-upload.py   # GitHub Contents API 推送
│   ├── _vla_expert.py          # 共享 LLM 客户端 + 领域上下文模块
│   └── SCRIPTS.md              # 完整 pipeline DAG 文档
│
├── config/
│   ├── active-config.template.json  # ← 从这里开始：RSS 源、关键词、领域设置
│   ├── assumptions.template.json    # 领域假设配置模板
│   ├── github-config.template.json  # GitHub 推送目标配置模板
│   └── jobs.template.json           # Cron job 配置
│
├── memory/                     # 本地知识存储（.gitignored，运行时自动创建）
│   ├── active-config.json      # 你的领域配置（从模板创建）
│   ├── assumptions.json        # 领域假设 + 置信度
│   ├── watchdog-log.json       # Watchdog 运行日志
│   ├── tmp/                    # Pipeline 中间产物（60 天自动清理）
│   └── github-config-*.json    # GitHub 推送目标（从模板创建）
│
├── docs/
│   └── banner.svg
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
**选 MineContext**：捕捉你自己读过的内容——完全本地，保护隐私。
**选 Pulsar**：需要服务器侧自主运行、持续生成结构化知识资产、故障自愈、月度自我校准的 pipeline。

| 维度 | Feedly AI | ResearchRabbit | MineContext | **Pulsar** |
|------|-----------|---------------|-------------|------------|
| **最擅长** | 团队情报订阅、移动端 | 学术引用图谱 | 个人上下文捕捉 | 自主领域情报 pipeline |
| **部署方式** | ☁️ 仅 SaaS | ☁️ 仅 SaaS | ✅ 本地 / 开源 | ✅ 自托管 / 开源 |
| **费用** | \$1,600–3,200 / 月 | 封闭定价 | 免费 | 免费 |
| **配置成本** | ✅ 零配置 | ✅ 零配置 | ✅ 桌面安装 | ⚠️ 约 1 小时 |
| **LLM 提供商** | ❌ 固定 | ❌ 固定 | ❌ 固定 | ✅ 任何 OpenAI 兼容 |
| **RSS 可配置** | ⚠️ 有限 | ❌ | ❌ | ✅ 任何 feed URL |
| **研究领域** | ⚠️ 话题过滤 | ❌ | ❌ | ✅ 完全自定义 |
| **信号评分** | ❌ | ❌ | ❌ | ✅ ⚡/🔧/📖/❌ LLM 前截断 |
| **推理透明度** | ❌ 黑盒摘要 | ❌ | ❌ | ✅ 三段可观测链路 |
| **故障自愈** | ❌ | ❌ | ❌ | ✅ 7 条自动恢复路径 |
| **信念校准** | ❌ | ❌ | ❌ | ✅ 假设，月度更新 |
| **预测追踪** | ❌ | ❌ | ❌ | ✅ 每两周 ✅/❌ 历史验证 |
| **知识输出** | 订阅流 / 收件箱 | 图谱视图 | 本地摘要 | 结构化 Markdown → Git |
| **硬件需求** | N/A（云端） | N/A（云端） | 桌面应用 | **2 GB RAM VPS** |

---

## 仿生认知架构

Pulsar 的内部分层参考认知有机体设计，而非传统数据管道：

| 认知层 | 生物类比 | Pulsar 组件 |
|--------|---------|------------|
| **感知层** | 感觉器官 | 可配置的 RSS 源 · GitHub releases · 社区讨论 |
| **过滤层** | 丘脑闸门 | 评分引擎（⚡/🔧/📖/❌）— 噪音在 LLM 前截断 |
| **推理层** | 皮层处理 | 三段式 LLM：prep → agent → post |
| **记忆层** | 海马体编码 | 结构化 Markdown → GitHub |
| **元认知层** | 前额叶反思 | 双周预测回顾 · 月度假设校准 |
| **免疫系统** | 自身免疫 | Watchdog：15 项健康检查，7 条自愈路径 |

---

## 参考部署：关键数字

内置配置同时追踪两个领域（VLA 机器人 + AI 开发工具），以下数字反映这一双领域部署规模：

| 指标 | 数值 |
|------|------|
| 自动排程任务 | **33** 个 cron job，覆盖两个研究领域 |
| Pipeline 脚本 | **55** 个，覆盖 VLA 和 AI 两条 pipeline |
| 追踪假设 | **19** 条，月度置信度自动更新 |
| Watchdog 检查 | **15** 项健康指标，**7** 条自愈路径 |
| 端到端延迟 | **< 2 小时**：RSS → 评分完成 → TG 推送 |
| 知识保留 | 社交情报 / hotspots **90 天**滚动 · 报告永久 Git 存档 |
| 硬件需求 | **2 GB RAM**，最低配 VPS 即可运行 |

单领域部署大约只需一半的脚本和 cron job 数量。

---

## 参考输出知识库

参考部署每天向以下两个公开仓库输出内容：

| 仓库 | 领域 | 主要内容 |
|------|------|---------|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | 机器人 · VLA 研究 | 每日论文评分 · 理论深度解析 · 双周预测报告 |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | AI 应用 · Agent 工具 | 工具日报 · 框架架构评审 · 每日精选 |

要接入你自己的仓库，编辑 `memory/github-config-*.json`（从 `config/github-config.template.json` 复制）。

---
## 更新日志

### 2026-02-28 — P0 基础设施版本

| 功能 | 说明 |
|------|------|
| **MCP Server** | 11 个工具的 MCP 服务端，将完整知识库暴露给 Claude Desktop / Cursor 等 MCP 客户端——在对话中直接查询 VLA 信号、SOTA、发布动态、社交情报、预测与管道健康状态 |
| [**多域配置**](docs/use-cases/multi-domain-config.md) | `memory/domains.json` 注册表 + `scripts/_domain_loader.py` 共享加载器——新增第三个研究域只需修改一个文件，无需改动现有脚本 |
| **一键部署** | `scripts/setup.sh` — 6 步引导式安装（Python 检查、`mcp` 安装、交互式配置提示、配置文件生成、路径替换、验证 + Claude Desktop JSON 输出） |


## 进阶阅读

| 文档 | 内容 |
|------|------|
| [AGENTS.md](AGENTS.md) | 完整部署指南：密钥配置 · 路径说明 · 常见问题 |
| [scripts/SCRIPTS.md](scripts/SCRIPTS.md) | 所有 pipeline 脚本的完整 DAG 图 · 每个脚本的输入输出 |
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | 参考 VLA 知识库（实时输出） |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | 参考 AI 工具知识库（实时输出） |

---

---

## 路线图

Pulsar 正从单域 pipeline 工具演进为**自演化领域情报平台**——在 AI Swarm 与 Agentic RAG 浪潮席卷 2026–2027 年的背景下，定义"个人域情报"这一细分领域的标准。

下表汇集了三个视角（产品战略、工程约束、研究员实用性）的辩论结论，并为每项优先级决策标注了背后的修改原因。

| 优先级 | 功能 | 描述 | 修改原因 | 状态 |
|--------|------|------|---------|------|
| **P0** | **MCP Server** | 将 Pulsar 的知识库、信号历史和假设置信度作为 MCP 端点暴露，可被 Claude、Cursor 或任何 MCP 兼容客户端直接查询 | 战略护城河：没有任何竞品（n8n、Dify、RAGFlow）提供"领域知识 MCP 端点"。将 Pulsar 从"脚本集合"升级为可查询的情报基础设施；使任何下游 AI 工具无需定制集成即可具备领域感知能力 | ✅ Done |
| **P0** | [**多域配置**](docs/use-cases/multi-domain-config.md) | 在同一调度与交付层下扩展至 N 个域，每个域拥有独立的配置文件和内存路径 | 所有跨域功能的结构性前提；配置层已部分支持，需要 pipeline 统一化和路由逻辑 | ✅ Done |
| **P0** | [**一键部署脚本**](docs/use-cases/one-click-deploy.md) | 交互式 `setup.sh`，在单次引导运行中完成 `.env`、`active-config.json`、GitHub 配置和首次 cron 加载的全部搭建 | 将复制部署的摩擦从约 1 小时降至数分钟；社区采用率取决于此；第一印象决定是否有人真正克隆并运行 | ✅ Done |
| **P1** | [**质量漂移检测器**](docs/use-cases/quality-drift-detector.md) | 追踪每个信号源的信号密度、评分分布和 LLM 输出质量；当指标连续 3 天以上系统性下降时告警 | 比峰值检测更根本：峰值是单点事件，漂移是无声的系统性退化。Watchdog 已能检测"是否运行"，漂移检测解决"产出内容是否仍有意义"这一更深层问题 | ✅ 已完成 |
| **P1** | [**Agent 角色切换**](docs/use-cases/agent-role-switching.md) *（需 4 GB RAM）* | 将三阶段链重构为具名角色——Reader、Analyst、Memory、Delivery——顺序执行；每个角色可使用不同规模的模型 | 顺序角色切换（而非真正的并行 swarm）是兼容 2 GB 服务器的唯一架构。价值在于模型级精准匹配：Reader 用廉价模型，Analyst 用强模型，无需重写整个 pipeline | ✅ 已完成 |
| **P1** | [**跨域规则引擎**](docs/use-cases/cross-domain-rule-engine.md) | 用户定义确定性规则实现跨域信号桥接：`IF vla_rating:⚡ AND keyword IN ["diffusion", "flow matching"] THEN flag_for_ai_app_review` | LLM 自由发现跨域关联假阳性率过高（"两个领域都提到了 transformer"）。确定性规则可审计、可预测，且编码了用户自身的跨域假设，而非让模型去猜测 | ✅ 已完成 |
| **P2** | **峰值检测器** | 当某关键词的信号密度在 24 小时内超过 7 日基线的 3 倍时，立即触发计划外推送，绕过日报批次 | 日报批次对 ⚡ 级事件响应不足：顶会论文发布后数小时内社区已展开讨论，隔天日报为时已晚。峰值检测在不替换批次 pipeline 的前提下恢复时效性 | 📋 计划中 |
| **P2** | **魔鬼代言人报告** | 每份推理报告通过独立的对抗性 Agent 轮次自动附加"最强反驳"章节 | 替代"辩论模式"：用户不需要阅读完整辩论，他们需要的是 2 句话的最强质疑。在不增加报告篇幅的前提下降低输出中的确认偏差；原有框架增加了 UX 摩擦而无分析收益 | 📋 计划中 |
| **P2** | [**实体追踪器**](docs/use-cases/entity-tracker.md) | 从每个 ⚡/🔧 评级信号中提取 `{作者, 机构, 基准, 方法名}`，写入结构化 JSON 索引，在 90 天滚动窗口内可查询 | 以极低成本覆盖 80% 的知识图谱需求。回答"这个 lab 过去 3 个月发了什么"需要的是索引，而非完整 GraphRAG——且此索引可增量构建，无前置批量成本 | 📋 计划中 |
| **P2** | **上游信号监控器** | 追踪 1–2 个上游领域（如机器人领域的计算机视觉、生物医学领域的材料科学）中历史上先于本领域突破出现的信号；仅标记，不做深度分析 | 领域突破很少源于领域内部：扩散模型来自图像生成，而非机器人学。上游监控以近乎零的额外 pipeline 成本，提供 1–3 个月的前瞻信号 | 📋 计划中 |
| **P2** | [**语义记忆搜索**](docs/use-cases/semantic-memory-search.md) | 对 60 天知识窗口构建向量索引；支持自然语言查询，如"上个月什么内容反驳了假设 V-003？" | 填补文件式存储与真正知识检索之间的空白。没有此功能，跨报告推理需要重新读取所有历史输出；有了它，系统可以回答关于自身历史的问题 | 📋 计划中 |
| **P3** | **GraphRAG 知识图谱** | 将 Git 提交历史和实体追踪器索引转化为关系图谱：论文 ↔ 作者 ↔ 基准 ↔ 机构 ↔ 方法；支持结构化图遍历查询 | 推迟：实体追踪器（P2）优先满足大多数检索需求。GraphRAG 的索引构建是 LLM 调用的 O(n²) 操作，仅在积累 6 个月以上数据或模型成本显著下降后才具备经济性 | 📋 计划中 |
| **P3** | **预测评分公开 API** | 将每个域的双周预测命中率和假设置信度作为可查询端点暴露——即领域情报来源的"可信度评分" | 使 Pulsar 的准确性声明可被独立验证。区别于所有无准确率记录的黑箱 AI 摘要工具；将预测循环转化为系统质量的公开信号 | 📋 计划中 |
| **P4** | [**配置与域模板商店**](docs/use-cases/config-marketplace.md) | 社区共享领域配置、假设模板、关键词集合和经验证的 cron 蓝图的集中平台 | 替代"联邦校准"（假设置信度与具体上下文强相关，在使用不同信号源、关键词和评分标准的实例间无法有意义地共享）。*可以*共享且立即有用的是*结构*：领域配置模板、RSS 订阅列表、假设入门集合 | 📋 计划中 |


## 致谢

Pulsar 构建在 [**Moltbot**](https://molt.bot)（前身 OpenClaw）之上——这是一个提供 cron 调度、LLM 路由和 Telegram 消息发送能力的 Agent 网关。没有 Moltbot 稳定可靠的调度和 Agent 运行时，Pulsar 的 33 个 cron job 全自动 pipeline 就无法实现。

感谢 [Moltbot](https://molt.bot) 团队构建并维护了 Pulsar 运行所依赖的基础设施。

---

## 社区 & 参与

有问题、有想法、想 Fork 改造成自己领域的版本？

- 💬 **提 Issue**：[GitHub Issues](https://github.com/sou350121/Pulsar/issues)
- 🔀 **Pull Request**：欢迎改进 pipeline、增加新领域支持、修复 bug
- 📡 **查看输出**：[VLA-Handbook](https://github.com/sou350121/VLA-Handbook) · [Agent-Playbook](https://github.com/sou350121/Agent-Playbook)

---

*MIT License — Fork 一份，改成你自己领域的 Pulsar。*
