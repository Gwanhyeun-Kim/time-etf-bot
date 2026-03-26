#!/bin/bash
# deploy_and_run.sh — LaunchAgent가 호출하는 래퍼 스크립트
# 1) Desktop 소스에서 최신 코드 동기화 (가능한 경우)
# 2) bot.py 실행
# 3) 실패 시 명확한 로그

DEPLOY_DIR="$HOME/time_etf_bot"
SOURCE_DIR="$HOME/Desktop/Claude/time_etf_bot"
LOG="$DEPLOY_DIR/bot.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] === deploy_and_run 시작 ===" >> "$LOG"

# 1) 소스에서 최신 파일 동기화 (Desktop 접근 가능한 경우만)
if [ -f "$SOURCE_DIR/bot.py" ]; then
    cp "$SOURCE_DIR/bot.py" "$DEPLOY_DIR/bot.py" 2>>"$LOG"
    cp "$SOURCE_DIR/.env" "$DEPLOY_DIR/.env" 2>>"$LOG"
    echo "[$TIMESTAMP] ✅ Desktop에서 동기화 완료" >> "$LOG"
else
    echo "[$TIMESTAMP] ⚠️ Desktop 접근 불가 (TCC). 기존 파일로 실행" >> "$LOG"
fi

# 2) .env 존재 확인
if [ ! -f "$DEPLOY_DIR/.env" ]; then
    echo "[$TIMESTAMP] ❌ .env 파일 없음! 발송 불가능" >> "$LOG"
    exit 1
fi

# 3) bot.py 실행
cd "$DEPLOY_DIR"
/usr/bin/python3 "$DEPLOY_DIR/bot.py" --now >> "$LOG" 2>&1
EXIT_CODE=$?

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
if [ $EXIT_CODE -ne 0 ]; then
    echo "[$TIMESTAMP] ❌ bot.py 비정상 종료 (exit code: $EXIT_CODE)" >> "$LOG"
fi

echo "[$TIMESTAMP] === deploy_and_run 종료 ===" >> "$LOG"
