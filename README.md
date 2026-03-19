# TIME ETF 구성종목 변동 알림 봇

TIME ETF 국내 8개 상품의 구성종목(주식 수량/비중) 변동을 감지하여 **텔레그램으로 알림**을 보냅니다.

## 준비사항

1. **텔레그램 봇 토큰** — `@BotFather`에서 발급
2. **알림 받을 채팅 ID** — 봇에 `/start` 메시지 후 확인
3. **`.env` 파일** 생성:
   ```
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHAT_IDS=id1,id2
   ```
4. **Python 패키지 설치**:
   ```bash
   pip install -r requirements.txt
   ```

## 실행 방법

```bash
# 즉시 1회 실행
python bot.py --now

# chat_id 확인
python bot.py --get-chatid
```

## 자동 발송 (macOS LaunchAgent)

`~/Library/LaunchAgents/com.jason.timeetfbot.plist`로 등록되어 있음.

- **매일 17:40** 자동 실행
- **맥북 재시작 시** 오늘 미발송이면 로그인 시 자동 실행 (`RunAtLoad`)
- 중복 발송 방지: `.last_run` 파일로 당일 발송 여부 체크

## 상태 파일

- `state.json` — 이전 조회 결과 (구성종목 수량/비중)
- `.last_run` — 마지막 발송 날짜 (중복 방지용)
- `bot.log` — 실행 로그

## 대상 ETF (8종)

코스닥액티브, Korea플러스배당액티브, 코스피액티브, 코리아밸류업액티브, K신재생에너지액티브, K바이오액티브, K이노베이션액티브, K컬처액티브
