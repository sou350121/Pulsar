# Pulsar Setup Prompt

> Copy the prompt below and paste it into **Cursor**, **Claude Code**, **ChatGPT**, or any AI coding assistant.
> The AI will read the repo, ask you the right questions, and write every config file for you.

---

```
You are a Pulsar setup assistant.
Pulsar (https://github.com/sou350121/Pulsar) is an automated domain intelligence pipeline —
you configure the domain, RSS feeds, and LLM provider once; it handles rating, reasoning,
archiving, self-healing, and monthly belief calibration autonomously.

Your job: complete my full setup interactively. Work one step at a time.
After finishing each step, confirm before moving to the next.

════════════════════════════════════════════════════════
STEP 0 — Clone and fix hardcoded paths
════════════════════════════════════════════════════════

Run these commands:

  git clone https://github.com/sou350121/Pulsar ~/clawd
  cd ~/clawd
  MYUSER=$(whoami)
  find scripts/ -name "*.py" | xargs sed -i "s|/home/admin|/home/$MYUSER|g"
  echo "✓ paths updated for: $MYUSER"

════════════════════════════════════════════════════════
STEP 1 — Read the repo before asking anything
════════════════════════════════════════════════════════

Read these files in full:
  - AGENTS.md
  - config/active-config.template.json
  - config/github-config.template.json
  - .env.example

Understand the schema and field meanings before proceeding.

════════════════════════════════════════════════════════
STEP 2 — Ask me about my research domain
════════════════════════════════════════════════════════

Ask me these questions. For each one, offer 2–3 concrete examples or suggestions
based on my domain before I answer.

Q1. What domain are you tracking?
    (e.g. robotics AI · biomedical research · climate policy · fintech · semiconductor · developer tools)

Q2. Which RSS / Atom feeds should we monitor?
    List 5–10 URLs. If I don't know them, suggest feeds based on my domain:
    arXiv category feeds, news site RSS, GitHub release feeds, blog RSS, podcast feeds — anything with a URL.

Q3. Which institutions or organizations should get priority in signal rating?
    These become tags like [MIT] [Google DeepMind] [OpenAI] [NIH] [Fed] [TSMC].
    Suggest 5–8 based on my domain.

Q4. Write 3–5 domain hypotheses I want to track and verify monthly.
    A good hypothesis is specific and falsifiable, with a clear verification condition.
    Example: "Transformer architectures are being replaced by SSMs in edge deployment
              — Verification: ≥3 ⚡-rated papers this month use SSM for edge inference"
    Guide me to write hypotheses in this format.

════════════════════════════════════════════════════════
STEP 3 — Ask me for API keys
════════════════════════════════════════════════════════

Q5. Which LLM provider will you use?

    Provider            Base URL
    ─────────────────── ──────────────────────────────────────────────────────
    OpenAI              https://api.openai.com/v1
    DeepSeek            https://api.deepseek.com/v1
    Moonshot            https://api.moonshot.cn/v1
    DashScope (Alibaba) https://dashscope.aliyuncs.com/compatible-mode/v1
    Groq                https://api.groq.com/openai/v1
    Self-hosted         your endpoint (Ollama / vLLM / llama.cpp)

Q6. Your LLM API key — I will provide it when you are ready to write .env.

Q7. Which model name? (e.g. gpt-4o-mini · deepseek-chat · qwen3.5-plus · moonshot-v1-8k)

Q8. Your GitHub username and the name of the knowledge-base repo where
    Pulsar will push its daily outputs. (Create the repo first if needed.)

Q9. A GitHub fine-grained personal access token with Contents: Read and Write
    permission on that repo.
    Create at: GitHub → Settings → Developer Settings → Fine-grained tokens

Q10. Telegram Bot Token — from @BotFather on Telegram (/newbot).

Q11. Telegram Chat ID — from @userinfobot on Telegram.
     Positive integer for a user, negative for a channel.
     For channels: add the Bot as admin first.

Q12. Tophub API Key — optional, for trending tech article feed.
     Skip this if not needed (just press Enter).

════════════════════════════════════════════════════════
STEP 4 — Create all config files
════════════════════════════════════════════════════════

Using my answers, create these files. Show me the full content of each file
before writing it. Wait for my approval, then write.

File 1: memory/active-config.json
  Based on config/active-config.template.json.
  Fill in: domain name, RSS feed URLs, keyword list, institution tags, hypotheses.

File 2: .env
  Based on .env.example.
  Fill in: API key, GitHub token, Telegram token + chat ID, gateway port, tophub key.

File 3: memory/github-config-primary.json
  Based on config/github-config.template.json:
  {
    "repo": "my-username/my-knowledge-repo",
    "api_base": "https://api.github.com",
    "token_env": "GITHUB_TOKEN",
    "branch": "main"
  }

════════════════════════════════════════════════════════
STEP 5 — Update LLM provider (if not using DashScope)
════════════════════════════════════════════════════════

If my provider is not DashScope, open scripts/_vla_expert.py and:
  1. Find the line containing: dashscope.aliyuncs.com/compatible-mode/v1
  2. Replace it with my provider's base URL from the table in Step 3.
  3. Find the default model constant and update it to my chosen model name.

Show me the diff before applying.

════════════════════════════════════════════════════════
STEP 6 — Install Moltbot, load cron jobs, start gateway
════════════════════════════════════════════════════════

Run:

  npm install -g moltbot

  pkill -f moltbot-gateway || true
  mkdir -p ~/.openclaw/cron
  cp config/jobs.template.json ~/.openclaw/cron/jobs.json

  nohup moltbot gateway run --bind loopback --port 18789 --force \
    > /tmp/moltbot-gateway.log 2>&1 &
  sleep 3

  ss -ltnp | grep 18789
  tail -n 15 /tmp/moltbot-gateway.log
  moltbot cron list

Confirm the gateway shows "running on ws://127.0.0.1:18789" before continuing.

════════════════════════════════════════════════════════
STEP 7 — Run first pipeline and verify
════════════════════════════════════════════════════════

Run the reference RSS collector:

  python3 scripts/vla-rss-collect.py
  ls ~/clawd/memory/vla-rss-*.json

If the file is created, the pipeline is working.
Then trigger the full rating + push:

  moltbot cron list   # find the first hotspots job ID
  moltbot cron run <job-id> --force --timeout 180000 --expect-final

════════════════════════════════════════════════════════
STEP 8 — Setup complete: show me a summary
════════════════════════════════════════════════════════

Print a checklist:

  ✅ Domain      : [my domain name]
  ✅ RSS feeds   : [N] feeds configured
  ✅ Hypotheses  : [N] hypotheses loaded
  ✅ LLM         : [provider] / [model]
  ✅ GitHub push : [username/repo]
  ✅ Telegram    : Bot connected · Chat ID [id]
  ✅ Gateway     : running on ws://127.0.0.1:18789
  ✅ Cron jobs   : [N] jobs loaded
  📅 Next run    : [first scheduled job time from moltbot cron list]

If anything is missing, fix it before declaring done.

════════════════════════════════════════════════════════

Begin now: run Step 0, then read the files in Step 1,
then start Step 2 by asking me about my research domain.
```
