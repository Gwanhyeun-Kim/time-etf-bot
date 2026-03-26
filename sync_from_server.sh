#!/bin/bash
# 서버에서 최신 파일 가져오기 (오늘 17:45 이후 아직 동기화 안 했을 때만)
SERVER="opc@161.118.199.90"
KEY="$HOME/Desktop/Claude/oracle-server/oracle-ssh.key"
LOCAL="$HOME/Desktop/Claude/time_etf_bot"
DEPLOY="$HOME/time_etf_bot"
SYNC_MARKER="$LOCAL/.last_sync"
TODAY=$(date '+%Y-%m-%d')
NOW_HOUR=$(date '+%H')
NOW_MIN=$(date '+%M')

# 오늘 16:00 이전이면 아직 봇 안 돌았으니 스킵
if [ "$NOW_HOUR" -lt 16 ] || ([ "$NOW_HOUR" -eq 16 ] && [ "$NOW_MIN" -lt 5 ]); then
    exit 0
fi

# 오늘 이미 동기화했으면 스킵
if [ -f "$SYNC_MARKER" ] && [ "$(cat "$SYNC_MARKER")" = "$TODAY" ]; then
    exit 0
fi

# 서버에서 파일 동기화
scp -i "$KEY" -o ConnectTimeout=10 "$SERVER:~/state.json" "$LOCAL/state.json" 2>/dev/null
scp -i "$KEY" -o ConnectTimeout=10 "$SERVER:~/bot.log" "$LOCAL/bot.log" 2>/dev/null
scp -i "$KEY" -o ConnectTimeout=10 "$SERVER:~/.last_run" "$LOCAL/.last_run" 2>/dev/null
scp -i "$KEY" -o ConnectTimeout=10 "$SERVER:~/state_weekly.json" "$LOCAL/state_weekly.json" 2>/dev/null

# 로컬 배포 폴더에도 복사
cp "$LOCAL/state.json" "$DEPLOY/state.json" 2>/dev/null
cp "$LOCAL/bot.log" "$DEPLOY/bot.log" 2>/dev/null
cp "$LOCAL/.last_run" "$DEPLOY/.last_run" 2>/dev/null

# 오늘 동기화 완료 마크
echo "$TODAY" > "$SYNC_MARKER"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 서버 동기화 완료" >> "$LOCAL/sync.log"
