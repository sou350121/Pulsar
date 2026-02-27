#!/bin/bash
# System-level Moltbot Gateway monitor
# Independent of Moltbot, runs via system crontab

# Check if openclaw or moltbot processes are running
if ! pgrep -f "openclaw\|moltbot" > /dev/null; then
    # Send Telegram alert
    curl -s -X POST "https://api.telegram.org/bot8463255635:AAHmL_-bka1GXXhP57u5sJAL5i74Lff73qA/sendMessage" \
         -d "chat_id=1898430254&text=⚠️ Moltbot Gateway 掛了！"
fi