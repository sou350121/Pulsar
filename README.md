# Pulsar · 照見

**自动把 AI/VLA 领域原始信号提炼成可推理知识资产的完整 pipeline 系统。**

> Fork 本仓库 + 配置环境变量 + 导入 cron jobs → 一台新机器完整运行整套 pipeline

---

## 系统概览

Pulsar（照见）由两条并行 pipeline 组成，共用同一台 Moltbot 网关：

```
VLA Pipeline                          AI Agent Pipeline
────────────────────────────────      ──────────────────────────────────
vla-rss-collect.py                    ai-app-rss-collect.py
  ↓                                     ↓
rate-vla-daily.py (⚡/🔧/📖/❌)        prep-ai-app-rss-filtered.py
  ↓                                     ↓
run-vla-daily-two-phase.py → TG       write-ai-app-daily.py → GitHub
  ↓
prep-vla-theory.py → agent → post     prep-ai-app-social.py → run → TG
prep-vla-social.py → run → post       prep-ai-deep-dive.py → agent → post
prep-vla-sota.py   → run → post       prep-ai-app-workflow.py → run → TG
prep-vla-release.py → run → post      run-ai-weekly-two-phase.py → TG
prep-vla-weekly.py → run → post
  ↓
daily-watchdog.py (self-healing)      prep-calibration-check.py (daily)
                                      monthly-calibration-agg.py
```

## 依赖

- **Node 22+** + **Moltbot** (`npm i -g moltbot@latest`)
- **Python 3.9+**（标准库 + `requests` 可选）
- **DashScope API key**（阿里云 Qwen 模型）
- **GitHub Token**（写入 VLA-Handbook 和 Agent-Playbook）
- **Telegram Bot Token**

## 快速开始

### 1. 克隆并配置环境变量

```bash
git clone https://github.com/sou350121/Pulsar-KenVersion.git
cd Pulsar-KenVersion
cp .env.example .env
# 编辑 .env，填入你的 API keys
```

### 2. 安装并启动 Moltbot 网关

```bash
npm i -g moltbot@latest
moltbot config set gateway.mode=local
moltbot channels connect telegram   # 输入 bot token
# 启动网关（后台）
nohup moltbot gateway run --bind loopback --port 18789 --force > /tmp/moltbot-gateway.log 2>&1 &
```

### 3. 复制脚本到工作目录

```bash
mkdir -p ~/clawd/scripts ~/clawd/memory/tmp
cp scripts/* ~/clawd/scripts/
```

### 4. 配置 GitHub 推送目标

编辑 `config/github-config.template.json`，填入你的 GitHub token 和目标 repo，保存为 `~/clawd/memory/github-config.json`。

### 5. 导入 cron jobs

```bash
# 编辑 config/jobs.template.json
# - 将 YOUR_TELEGRAM_CHAT_ID 替换为你的 Telegram chat ID
# - 调整 schedule（时区默认 Asia/Shanghai）
# 导入到 Moltbot
moltbot cron import config/jobs.template.json
```

### 6. 验证

```bash
moltbot channels status --probe
moltbot cron list
tail -f /tmp/moltbot-gateway.log
```

## 配置文件说明

| 文件 | 说明 |
|---|---|
| `config/jobs.template.json` | 定时任务模板（sanitized） |
| `config/active-config.template.json` | AI Agent 监控参数（关键词/过滤规则） |
| `config/assumptions.template.json` | Calibration 假设定义 |
| `config/github-config.template.json` | GitHub 推送目标配置 |
| `.env.example` | 所有需要的环境变量 |

## 脚本参考

见 [`scripts/SCRIPTS.md`](./scripts/SCRIPTS.md) — 完整命名规则与 DAG 拓扑。

## 输出目标

- **Telegram**：每日 VLA 热点、社交情报、AI 日报、精选、工作流灵感
- **GitHub VLA-Handbook**：论文深度解析、weekly/biweekly 报告
- **GitHub Agent-Playbook**：工具条目（app_index.md）、Deep Dive、biweekly

## 相关仓库

- [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) — VLA 知识库（pipeline 输出目标之一）
- [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) — AI 应用监控知识库（pipeline 输出目标之一）

## 许可证

MIT
