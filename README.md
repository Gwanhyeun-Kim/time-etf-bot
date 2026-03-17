# TIME ETF 구성종목 변동 알림 봇

이 스크립트는 **TIME ETF 국내 8개** 상품의 구성종목(주식 수량) 변동을 감지하여 **텔레그램으로 알림**을 보냅니다.

## ✅ 준비사항

1. **텔레그램 봇 토큰**
   - `@BotFather`에서 `/newbot` 입력 후 생성
   - 발급받은 토큰을 `TELEGRAM_BOT_TOKEN` 환경 변수로 설정

2. **알림 받을 채팅 ID**
   - 본인과의 1:1 대화 ID 또는 그룹 ID를 사용
   - 봇과 대화를 시작한 후 [@userinfobot](https://t.me/userinfobot) 등으로 `chat_id`를 확인
   - `TELEGRAM_CHAT_ID` 환경 변수로 설정

3. **Python 환경**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## 🧠 실행 방법

### 1) 1회 실행 (cron / 스케줄러에서 사용)
```bash
python bot.py --mode once
```

### 2) 지속 실행 (PC 켜져 있는 동안 계속 감시)
```bash
python bot.py --mode poll --interval 60
```
- `--interval`은 체크 주기(분)입니다.

## 🔎 업데이트 시점 (예상)
- 사이트에는 **기준일**만 표시되고 시간이 없으므로 정확한 업데이트 시간은 공개되어 있지 않습니다.
- 일반적으로 **국내 주식시장 마감 직후(16:00~18:00 KST)**에 데이터가 갱신되는 경우가 많습니다.
- Cron으로 매일 **18:00~19:00 사이**에 `--mode once`로 실행하도록 설정하면 무난합니다.

## 🔧 상태 저장
- 이전 조회 결과는 `state.json`에 저장됩니다.
- 다음 실행 시 기존 구성종목 수량과 변동 여부를 비교하여 알림을 보냅니다.

## ✨ 커스터마이징 아이디어
- 알림 대상 ETF 목록을 더 추가하거나 제거할 수 있습니다. (`bot.py`의 `ETF_LIST` 수정)
- 변화가 있는 종목만 정리해 요약 메시지로 발송하도록 포맷을 조정할 수 있습니다.
