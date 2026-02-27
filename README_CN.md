<div align="center">

<picture>
  <img alt="Pulsar · 照見" src="docs/banner.svg" width="100%" height="auto">
</picture>

### Pulsar · 照見：自动化领域情报 Pipeline

[English](README.md) · [中文](#)

<a href="https://github.com/sou350121/VLA-Handbook">VLA-Handbook</a> · <a href="https://github.com/sou350121/Agent-Playbook">Agent-Playbook</a> · <a href="https://github.com/sou350121/Pulsar-KenVersion/issues">Issues</a>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Moltbot](https://img.shields.io/badge/Powered%20by-Moltbot-purple)](https://molt.bot)
[![Pipeline](https://img.shields.io/badge/Pipeline-33%20个定时任务-green)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

</div>

---

## 概述

### "上下文捕获"工具解决不了的问题

[MineContext](https://github.com/volcengine/MineContext) 这类工具擅长做一件事：捕获你的*个人行为*（屏幕截图、文档），并在你的 AI 会话中将其浮现出来。这解决的是**个人记忆**问题。

但如果你是一个需要持续追踪某个高速演进领域的研究者或工程师——VLA 机器人、AI Agent 生态——真正的问题其实是另一回事：

- **领域信号过于分散**：arXiv、GitHub Release、社区争论、社交媒体、Benchmark 更新——没有任何单一订阅能覆盖全部。
- **原始信号全是噪音**：每天 30 篇论文，90% 不相关。你需要的是过滤、评级和解读，而不是聚合。
- **上下文捕获 ≠ 知识资产**：你读过的截图不会变成结构化、可检索、可引用的知识。
- **没有认知闭环**：你读到一个趋势，形成一个判断，然后就继续往前走了。没有任何系统来跟踪你的判断是否准确。

### Pulsar 的解法

**Pulsar（照见）** 是一个服务端的领域情报 Pipeline。它不是捕获你做了什么，而是 24/7 监控一个领域，按计划运行 LLM 分析，并自动将结构化知识资产写入 GitHub 和 Telegram。

- **信号进入前先评级** → **把噪音切成信号**：每篇论文在进入深度 Pipeline 前先被评为 ⚡/🔧/📖/❌。只有战略级内容才进行 LLM 分析。
- **分阶段 LLM 架构** → **深度而不幻觉**：`prep → agent → post` 三阶段设计，把采集、生成与确定性输出分离。
- **定时情报** → **知识持续复利**：33 个定时任务每天写入两个结构化 GitHub 仓库。内容积累并形成交叉引用。
- **自愈 Watchdog** → **没有静默失败**：`daily-watchdog.py` 监控 15 个 Pipeline 健康信号，自动触发 RSS 失败、LLM 超时和孤立 Phase 的恢复。
- **认知校准闭环** → **信念可验证**：双周报告给出可验证的预测，下期回顾打分 ✅/❌/⏳，月度聚合更新 19 个追踪假设的置信度。

---

## 🆚 与同类工具的差异

### vs MineContext

| 维度 | MineContext | Pulsar |
|---|---|---|
| **监控对象** | 你的个人行为（屏幕、文档） | 一个领域（VLA 研究 + AI App 生态） |
| **谁来驱动** | 你——它捕获你的操作 | 自主运行——按计划，无需人工触发 |
| **输出** | 浮现到你的 AI 会话的上下文 | 结构化知识资产（GitHub 仓库 + Telegram） |
| **架构** | 桌面应用（Mac/Windows） | 服务端 Pipeline（33 个定时任务） |
| **深度** | 捕获 → 存储 → 检索 | 采集 → 评级 → LLM 分析 → 写入 → 校准 |
| **认知层** | 无 | 双周预测 + 月度回测 |
| **使用场景** | "我上周读了什么？" | "这个领域本周发生了什么？我的判断还准吗？" |

> MineContext 回答的是：*"我的上下文是什么？"*  
> Pulsar 回答的是：*"这个领域正在发生什么，我的认知模型还准确吗？"*

---

## 🏗 架构

```
                    ┌─────────────────────────────────────┐
                    │           PULSAR PIPELINE            │
                    └─────────────────────────────────────┘

信号层                        处理层                      输出层
────────────                  ────────────────            ────────────
arXiv RSS                     rate-vla-daily.py           → Telegram
GitHub Release    ──────►     ⚡/🔧/📖/❌ 评级  ──────►   每日热点
社区讨论                      prep → agent → post         社交情报
社交媒体 / 网页               两阶段 LLM 运行器           周报

AI App RSS                    prep-ai-*.py                → GitHub
工具发布          ──────►     run-ai-*-two-phase ──────►  VLA-Handbook
社区热议                      post-ai-*.py                Agent-Playbook
"I built X" 案例              专家策展                    app_index.md

                              ─────────────────
                              系统层
                              daily-watchdog.py      15 项检查 · 自愈
                              prep-calibration.py    每日假设扫描
                              monthly-calibration    置信度更新
```

### Pipeline 时间表（上海时间）

| 时间 | 任务 |
|---|---|
| 06:45 | AI RSS 采集 |
| 07:00 | AI 日报 → `cognition/app_index.md` |
| 07:15 | AI 每日精选（web 搜索 + 编辑分级） |
| 07:45 | AI 社交情报（观点 / 争议 / 病毒传播） |
| 09:xx | VLA RSS → 评级 → 热点 → Telegram |
| 10:xx | VLA SOTA / Release / 社交情报 |
| 11:00 | Calibration 检查（19 个假设） |
| 15:30 周二/四/六 | AI Deep Dive → `cognition/frameworks/` |
| 15:45 周一/三/五/日 | AI 工作流灵感 |
| 周日 10:30 | 周度质量评审 + 风向洞察 |
| 每月 28 日 | 月度 Calibration 聚合 |

---

## 🚀 快速开始

### 前置依赖

- Node 22+ 和 [Moltbot](https://molt.bot)（`npm i -g moltbot@latest`）
- Python 3.9+
- DashScope API Key（阿里云 Qwen 模型）
- GitHub Token（对输出 Repo 有写权限）
- Telegram Bot Token

### 1. 克隆并配置环境变量

```bash
git clone https://github.com/sou350121/Pulsar-KenVersion.git
cd Pulsar-KenVersion
cp .env.example .env
# 填入你的 API Keys
```

### 2. 启动 Moltbot 网关

```bash
moltbot config set gateway.mode=local
moltbot channels connect telegram
nohup moltbot gateway run --bind loopback --port 18789 --force \
  > /tmp/moltbot-gateway.log 2>&1 &
moltbot channels status --probe
```

### 3. 部署脚本和配置

```bash
mkdir -p ~/clawd/scripts ~/clawd/memory/tmp
cp scripts/* ~/clawd/scripts/
cp config/github-config.template.json ~/clawd/memory/github-config.json
# 编辑 github-config.json：填入 token 和目标 Repo 名
```

### 4. 导入定时任务

```bash
# 编辑 config/jobs.template.json：
# - 将 YOUR_TELEGRAM_CHAT_ID 替换为你的 Telegram Chat ID
# - 按需调整时区和计划
moltbot cron import config/jobs.template.json
moltbot cron list   # 验证 33 个任务已导入
```

### 5. 端到端验证

```bash
moltbot cron run <job-id> --force --timeout 180000 --expect-final
tail -f /tmp/moltbot-gateway.log
```

---

## 📂 仓库结构

```
Pulsar-KenVersion/
├── scripts/                  # 55 个 Pipeline 脚本
│   ├── vla-rss-collect.py
│   ├── rate-vla-daily.py     # ⚡/🔧/📖/❌ 论文评级
│   ├── run-*-two-phase.py    # LLM Agent 运行器
│   ├── daily-watchdog.py     # 自愈监控（v6，15 项检查）
│   ├── prep-calibration-check.py
│   └── SCRIPTS.md            # 完整 DAG + 命名规范
├── config/
│   ├── jobs.template.json    # 33 个定时任务（已脱敏）
│   ├── active-config.template.json
│   ├── assumptions.template.json
│   └── github-config.template.json
├── .env.example
└── docs/
    └── banner.svg
```

---

## 📤 输出仓库

| 仓库 | Pulsar 写入内容 | 频率 |
|---|---|---|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | 论文深度解析、周报/双周报、SOTA 追踪 | 每日 + 每周 |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | 工具索引、Deep Dive、双周报、社交情报 | 每日 + 双周 |

---

## 🤝 贡献

欢迎 PR——新增信号源、LLM Pipeline 阶段或其他平台的输出适配器。

## 📄 许可证

MIT
