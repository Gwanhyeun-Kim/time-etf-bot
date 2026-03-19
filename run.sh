#!/bin/bash
cd /Users/jason/Desktop/Claude/time_etf_bot
set -a; source .env; set +a
/usr/bin/python3 bot.py --now >> /Users/jason/Desktop/Claude/time_etf_bot/bot.log 2>&1
