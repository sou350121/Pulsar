# Pulsar · 照見

**一個自我進化的領域情報有機體。**  
不是爬蟲，不是新聞聚合，是一個會看、會評、會推理——然後每個月變得更準的系統。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Lang](https://img.shields.io/badge/README-English-blue)](README.md)

---

## 核心理念

大多數監控工具只是「收集」。Pulsar 在**進化**。

每兩週，它回顧自己的預測，給每一條打分：✅ 驗證 / ❌ 落空 / ⏳ 待觀察。  
每個月，它根據真實發生的事情，重新校準 19 條追蹤假設的置信度。  
表現差的假設被列入 watch-list，下一輪循環自動注入更多相關信號。

**這個系統知道自己不知道什麼——然後去找答案。**

---

## 仿生認知架構

Pulsar 的設計靈感來自認知有機體，而非傳統數據管道：

| 認知層 | 生物類比 | Pulsar 組件 |
|--------|---------|------------|
| **感知層** | 感覺器官 | arXiv RSS · GitHub 發布 · 社區討論 |
| **過濾層** | 丘腦閘門 | 評分引擎（⚡/🔧/📖/❌）— 噪音在 LLM 前截斷 |
| **推理層** | 皮層處理 | 三段式 LLM：`prep → agent → post` |
| **記憶層** | 海馬體編碼 | 結構化 Markdown → GitHub（VLA-Handbook · Agent-Playbook）|
| **元認知層** | 前額葉反思 | 雙周預測回顧 · 月度校準 |
| **免疫系統** | 自身免疫 | Watchdog：15 項健康檢查，7 條自癒路徑 |

---

## 進化閉環

```
信號攝入 ─► 評分過濾 ─► LLM 推理 ─► 知識輸出
                                          │
                                    雙周預測報告
                                  （✅/❌/⏳ 歷史追蹤）
                                          │
                                    月度假設校準
                                  19 條置信度自動更新
                                          │
                                    Watch-list 強化
                                  薄弱假設獲得更多信號
                                          │
                                  ────────┘（回饋至信號攝入）
```

---

## 吹點數字

| 指標 | 數值 |
|------|------|
| 自動排程任務 | **33** 個 cron job，全自動，無需人工觸發 |
| Pipeline 腳本 | **55** 個，覆蓋兩個研究領域 |
| 追蹤假設 | **19** 條，月度自動更新置信度 |
| Watchdog 檢查 | **15** 項健康指標，**7** 條自癒恢復路徑 |
| 端到端延遲 | **< 2小時**：arXiv 原始 RSS → 評分論文 → TG 推送 |
| 硬件需求 | **2 GB RAM**，最低配 VPS 即可運行 |
| 輸出知識庫 | **2** 個 GitHub repo，每日 commit，完整歷史 |

---

## 和同類工具的差距

| 維度 | Feedly AI | ResearchRabbit | MineContext | **Pulsar** |
|------|-----------|---------------|-------------|------------|
| **定位** | 市場/威脅情報訂閱 | 論文引用圖譜 | 個人桌面上下文 | 領域情報 pipeline |
| **部署** | ☁️ 僅 SaaS | ☁️ 僅 SaaS | ✅ 本地 / 開源 | ✅ 自托管 / 開源 |
| **費用** | $1,600–3,200 / 月 | 封閉定價 | 免費 | 免費 |
| **信號評分** | ❌ | ❌ | ❌ | ✅ ⚡/🔧/📖/❌ LLM 前截斷 |
| **LLM 推理** | ⚠️ 摘要生成 | ❌ | ⚠️ 單次調用 | ✅ 三段式 pipeline |
| **自癒恢復** | ❌ | ❌ | ❌ | ✅ 7 條自動恢復路徑 |
| **信念校準** | ❌ | ❌ | ❌ | ✅ 19 條假設，月度更新 |
| **預測追蹤** | ❌ | ❌ | ❌ | ✅ 每兩週 ✅/❌ 歷史驗證 |
| **知識輸出** | 訂閱流 / 收件箱 | 圖譜視圖 | 本地摘要 | 結構化 Markdown → Git |
| **硬件需求** | N/A（雲端） | N/A（雲端） | 桌面應用 | **2 GB VPS** |

> Feedly AI 每月費用超過大多數工程師一週的薪水——但它仍然無法告訴你，它自己的判斷上個月有幾條是對的。

---

## Pipeline 全貌

```
arXiv RSS ───────────────────►┐
GitHub 發布 ─────────────────►│  評分（⚡/🔧/📖/❌）
社區討論 ───────────────────►│       │
社交信號 ───────────────────►┘       │
                                      ▼
                             三段式 LLM Pipeline
                             （prep → agent → post）
                                      │
                   ┌──────────────────┼──────────────────┐
                   ▼                  ▼                  ▼
            每日熱點論文       理論深度解析          校準檢查
                   │                  │                  │
                   └──────────────────┴──────────────────┘
                                      │
                             ┌────────┴────────┐
                             ▼                 ▼
                        VLA-Handbook     Agent-Playbook
                        Telegram 推送（兩個頻道）
```

---

## 快速部署

**依賴**：Node 22+ · Python 3.9+ · [Moltbot](https://molt.bot) · DashScope API Key · GitHub Token · Telegram Bot Token

```bash
git clone https://github.com/sou350121/Pulsar-KenVersion
cp config/.env.example .env           # 填入你的密鑰
moltbot gateway run --bind loopback --port 18789 --force
moltbot cron import config/jobs.template.json
python3 scripts/vla-rss-collect.py    # 測試單條 pipeline
```

完整部署文檔：[AGENTS.md](AGENTS.md)

---

## 輸出知識庫

| 倉庫 | 領域 | 包含內容 |
|------|------|---------|
| [VLA-Handbook](https://github.com/sou350121/VLA-Handbook) | 機器人 · VLA 研究 | 每日評分 · 理論解析 · 雙周預測報告 |
| [Agent-Playbook](https://github.com/sou350121/Agent-Playbook) | AI 應用 · Agent 工具 | 工具日報 · 框架評審 · 社交情報 |

---

*MIT License — Fork 一份，改成你自己領域的 Pulsar。*
