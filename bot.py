"""TIME ETF 국내 8개 구성종목 수량 변동을 매일 22시에 텔레그램으로 알리는 봇

Usage:
  python bot.py              # 매일 22:00 스케줄 실행
  python bot.py --now        # 즉시 1회 실행 (테스트용)
  python bot.py --get-chatid # chat_id 확인용
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
import schedule

# ── .env 로드 (LaunchAgent에서 bash 없이 직접 실행 시 필요) ────────────
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ── 설정 ──────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_IDS = [
    cid.strip()
    for cid in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",")
    if cid.strip()
]

ETF_LIST = [
    {"name": "코스닥액티브", "idx": 24},
    {"name": "Korea플러스배당액티브", "idx": 12},
    {"name": "코스피액티브", "idx": 11},
    {"name": "코리아밸류업액티브", "idx": 15},
    {"name": "K신재생에너지액티브", "idx": 16},
    {"name": "K바이오액티브", "idx": 13},
    {"name": "K이노베이션액티브", "idx": 17},
    {"name": "K컬처액티브", "idx": 1},
]

PAGE_URL = "https://timeetf.co.kr/m11_view.php"
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
LAST_RUN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_run")
REPORT_TIME = "17:40"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
})


# ── HTML 파싱 ─────────────────────────────────────────────────────────
def parse_holdings_html(html: str) -> list[dict]:
    """HTML에서 moreList1 테이블의 구성종목을 파싱하여 [{code, name, quantity}, ...] 반환."""
    from html.parser import HTMLParser

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_table = False
            self.in_cell = False
            self.rows = []
            self.current_row = []
            self.current_cell = ""

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            if tag == "table" and "moreList1" in attrs_dict.get("class", ""):
                self.in_table = True
            if self.in_table and tag in ("td", "th"):
                self.in_cell = True
                self.current_cell = ""
            if self.in_table and tag == "tr":
                self.current_row = []

        def handle_endtag(self, tag):
            if self.in_table and tag in ("td", "th"):
                self.in_cell = False
                self.current_row.append(self.current_cell.strip())
            if self.in_table and tag == "tr" and self.current_row:
                self.rows.append(self.current_row)
            if self.in_table and tag == "table":
                self.in_table = False

        def handle_data(self, data):
            if self.in_cell:
                self.current_cell += data

    p = TableParser()
    p.feed(html)

    holdings = []
    for row in p.rows:
        if len(row) < 3 or row[0] == "종목코드":
            continue
        code = row[0].strip()
        name = row[1].strip()
        if not code or name == "현금":
            continue
        qty_str = row[2].replace(",", "").strip()
        try:
            qty = int(qty_str)
        except ValueError:
            try:
                qty = int(float(qty_str))
            except ValueError:
                continue
        weight = 0.0
        if len(row) >= 5:
            try:
                weight = float(row[4].replace(",", "").strip())
            except ValueError:
                weight = 0.0
        holdings.append({"code": code, "name": name, "quantity": qty, "weight": weight})
    return holdings


def fetch_holdings(idx: int, date: str | None = None) -> list[dict]:
    """ETF idx에 대한 구성종목을 가져온다. date: 'YYYY-MM-DD' 형식 (None이면 오늘)."""
    params = {"idx": str(idx)}
    if date:
        params["pdfDate"] = date
    r = SESSION.get(PAGE_URL, params=params, timeout=30)
    r.raise_for_status()
    return parse_holdings_html(r.text)


# ── 상태 저장/로드 ───────────────────────────────────────────────────
def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ── 변동 비교 ────────────────────────────────────────────────────────
def diff_holdings(old: dict, new: list[dict]) -> dict:
    """수량 변동 비교. old: {code: {name, quantity}}, new: [{code, name, quantity}]
    반환: {code: {name, old_qty, new_qty, delta, status}}
    status: 'changed' | 'added' | 'removed'
    """
    new_map = {h["code"]: h for h in new}
    diffs = {}

    # 기존 종목 변동 + 신규 편입
    for code, item in new_map.items():
        if code in old:
            old_qty = old[code]["quantity"]
            new_qty = item["quantity"]
            old_weight = old[code].get("weight", 0.0)
            new_weight = item.get("weight", 0.0)
            if old_qty != new_qty:
                diffs[code] = {
                    "name": item["name"],
                    "old_qty": old_qty,
                    "new_qty": new_qty,
                    "delta": new_qty - old_qty,
                    "old_weight": old_weight,
                    "new_weight": new_weight,
                    "status": "changed",
                }
        else:
            diffs[code] = {
                "name": item["name"],
                "old_qty": 0,
                "new_qty": item["quantity"],
                "delta": item["quantity"],
                "old_weight": 0.0,
                "new_weight": item.get("weight", 0.0),
                "status": "added",
            }

    # 편출 종목
    for code, item in old.items():
        if code not in new_map:
            diffs[code] = {
                "name": item["name"],
                "old_qty": item["quantity"],
                "new_qty": 0,
                "delta": -item["quantity"],
                "old_weight": item.get("weight", 0.0),
                "new_weight": 0.0,
                "status": "removed",
            }

    return diffs


# ── 텔레그램 ─────────────────────────────────────────────────────────
def tg_api(method: str, **kwargs):
    """텔레그램 Bot API 호출."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    r = requests.post(url, json=kwargs, timeout=30)
    r.raise_for_status()
    return r.json()


def get_chat_id() -> str | None:
    """최근 메시지에서 chat_id를 가져온다."""
    result = tg_api("getUpdates", offset=-1, limit=1)
    updates = result.get("result", [])
    if not updates:
        return None
    msg = updates[-1].get("message", {})
    return str(msg.get("chat", {}).get("id", ""))


def send_message(chat_id: str, text: str):
    """텔레그램 메시지 전송 (Markdown). 길면 분할 전송."""
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        tg_api("sendMessage", chat_id=chat_id, text=text, parse_mode="Markdown")
        return

    # 긴 메시지 분할
    lines = text.split("\n")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > MAX_LEN:
            tg_api("sendMessage", chat_id=chat_id, text=chunk, parse_mode="Markdown")
            chunk = line + "\n"
        else:
            chunk += line + "\n"
    if chunk.strip():
        tg_api("sendMessage", chat_id=chat_id, text=chunk, parse_mode="Markdown")


# ── 리포트 생성 ──────────────────────────────────────────────────────
TOP_N = 10  # 상위 보유종목 표시 개수

def build_etf_report(name: str, holdings: list[dict], diffs: dict) -> str:
    """ETF 하나에 대한 리포트 블록 생성."""
    lines = [f"━━━━━━━━━━━━━━━━━━━━━━", f"*[ {name} ]*"]

    # 상위 보유종목 (비중 순)
    sorted_h = sorted(holdings, key=lambda h: h.get("weight", 0), reverse=True)
    lines.append("")
    lines.append("🏆 상위 보유종목")
    for i, h in enumerate(sorted_h[:TOP_N], 1):
        lines.append(f"  {i}. {h['name']} {h['weight']:.2f}% ({h['quantity']:,}주)")

    # 주요 변동
    if not diffs:
        lines.append("")
        lines.append("변동 없음 ✅")
        return "\n".join(lines)

    # 변동을 카테고리별로 분류
    added = {c: d for c, d in diffs.items() if d["status"] == "added"}
    removed = {c: d for c, d in diffs.items() if d["status"] == "removed"}
    changed = {c: d for c, d in diffs.items() if d["status"] == "changed"}

    lines.append("")
    lines.append("🔄 주요 변동 (전일 대비, 변동폭 순)")

    # 모든 변동을 합쳐서 변동폭(절대값) 큰 순으로 정렬
    all_diffs = list(diffs.items())
    all_diffs.sort(key=lambda t: abs(t[1]["delta"]), reverse=True)

    for code, d in all_diffs:
        sign = "+" if d["delta"] > 0 else ""
        w_delta = d["new_weight"] - d["old_weight"]
        w_sign = "+" if w_delta > 0 else ""
        if d["status"] == "added":
            lines.append(f"  🆕 {d['name']} | 신규 편입 {d['new_qty']:,}주 ({d['new_weight']:.2f}%)")
        elif d["status"] == "removed":
            lines.append(f"  ❌ {d['name']} | 편출 (-{d['old_qty']:,}주, {d['old_weight']:.2f}% → 0%)")
        else:
            arrow = "🔺" if d["delta"] > 0 else "🔻"
            lines.append(
                f"  {arrow} {d['name']} | {sign}{d['delta']:,}주 ({d['old_qty']:,} → {d['new_qty']:,}) | {w_sign}{w_delta:.2f}%p ({d['old_weight']:.2f} → {d['new_weight']:.2f}%)"
            )

    return "\n".join(lines)


# ── 인사이트 생성 ────────────────────────────────────────────────────
def build_insight(all_diffs_by_etf: dict) -> str:
    """전체 ETF 변동을 종합하여 핵심 인사이트 메시지 생성."""
    if not all_diffs_by_etf:
        return ""

    # 종목별로 어떤 ETF에서 어떤 변동이 있었는지 집계
    stock_actions = {}  # {name: {etfs: [], total_delta: int, status_list: []}}
    for etf_name, diffs in all_diffs_by_etf.items():
        for code, d in diffs.items():
            name = d["name"]
            if name not in stock_actions:
                stock_actions[name] = {"code": code, "etfs": [], "total_delta": 0, "statuses": []}
            stock_actions[name]["etfs"].append(etf_name)
            stock_actions[name]["total_delta"] += d["delta"]
            stock_actions[name]["statuses"].append(d["status"])

    lines = ["━━━━━━━━━━━━━━━━━━━━━━", "💡 *핵심 인사이트 요약*", ""]

    # 컨빅션 바이: 여러 ETF에서 동시에 증가하거나 편입된 종목
    conviction_buy = {k: v for k, v in stock_actions.items()
                      if v["total_delta"] > 0 and (len(v["etfs"]) >= 2 or "added" in v["statuses"])}
    # 컨빅션 셀: 여러 ETF에서 동시에 감소하거나 편출된 종목
    conviction_sell = {k: v for k, v in stock_actions.items()
                       if v["total_delta"] < 0 and (len(v["etfs"]) >= 2 or "removed" in v["statuses"])}
    # 단일 ETF 주요 변동 (위에 포함 안 된 것 중 변동폭 큰 것)
    single_moves = {k: v for k, v in stock_actions.items()
                    if k not in conviction_buy and k not in conviction_sell and abs(v["total_delta"]) > 0}

    if conviction_buy:
        lines.append("🟢 *컨빅션 매수 시그널*")
        for name, v in sorted(conviction_buy.items(), key=lambda t: t[1]["total_delta"], reverse=True):
            etf_str = ", ".join(v["etfs"])
            if "added" in v["statuses"]:
                lines.append(f"  • {name}: 신규 편입 (+{v['total_delta']:,}주)")
            else:
                lines.append(f"  • {name}: +{v['total_delta']:,}주")
            lines.append(f"    → {etf_str}")
        lines.append("")

    if conviction_sell:
        lines.append("🔴 *컨빅션 매도 시그널*")
        for name, v in sorted(conviction_sell.items(), key=lambda t: t[1]["total_delta"]):
            etf_str = ", ".join(v["etfs"])
            if "removed" in v["statuses"]:
                lines.append(f"  • {name}: 편출 ({v['total_delta']:,}주)")
            else:
                lines.append(f"  • {name}: {v['total_delta']:,}주")
            lines.append(f"    → {etf_str}")
        lines.append("")

    # 개별 ETF 내 주요 변동 (상위 5개만)
    if single_moves:
        top_singles = sorted(single_moves.items(), key=lambda t: abs(t[1]["total_delta"]), reverse=True)[:5]
        lines.append("📌 *개별 ETF 주요 변동*")
        for name, v in top_singles:
            sign = "+" if v["total_delta"] > 0 else ""
            emoji = "🔺" if v["total_delta"] > 0 else "🔻"
            lines.append(f"  {emoji} {name}: {sign}{v['total_delta']:,}주 ({v['etfs'][0]})")
        lines.append("")

    # 변동 ETF 수 / 전체 요약
    total_changes = sum(len(d) for d in all_diffs_by_etf.values())
    changed_etfs = len(all_diffs_by_etf)
    lines.append(f"📊 변동 ETF {changed_etfs}개 / 총 {total_changes}건 종목 변동")

    return "\n".join(lines)


# ── 중복 발송 방지 ────────────────────────────────────────────────────
def already_sent_today() -> bool:
    """오늘 이미 리포트를 보냈는지 확인."""
    today = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(LAST_RUN_PATH):
        with open(LAST_RUN_PATH, "r") as f:
            return f.read().strip() == today
    return False


def mark_sent_today():
    """오늘 발송 완료 기록."""
    with open(LAST_RUN_PATH, "w") as f:
        f.write(datetime.now().strftime("%Y-%m-%d"))


# ── 메인 로직 ────────────────────────────────────────────────────────
def check_and_report():
    """모든 국내 ETF를 체크하고 변동 사항을 텔레그램으로 보고."""
    if already_sent_today():
        print(f"[{datetime.now()}] 오늘 이미 발송됨. 스킵.")
        return

    chat_ids = TELEGRAM_CHAT_IDS

    state = load_state()
    new_state = {}
    report_parts = []
    today = datetime.now().strftime("%Y.%m.%d")
    has_any_data = False
    first_run = not any(k for k in state if k != "_chat_id")
    has_major_change = False
    all_diffs_by_etf = {}

    for etf in ETF_LIST:
        idx_key = str(etf["idx"])
        try:
            holdings = fetch_holdings(etf["idx"])
            has_any_data = True
        except Exception as e:
            print(f"[ERROR] {etf['name']} 데이터 수집 실패: {e}")
            if idx_key in state:
                new_state[idx_key] = state[idx_key]
            continue

        new_state[idx_key] = {
            h["code"]: {"name": h["name"], "quantity": h["quantity"], "weight": h.get("weight", 0.0)}
            for h in holdings
        }

        old_holdings = state.get(idx_key, {})
        diffs = diff_holdings(old_holdings, holdings) if not first_run else {}
        if diffs:
            has_major_change = True
            all_diffs_by_etf[etf["name"]] = diffs

        report_parts.append(build_etf_report(etf["name"], holdings, diffs))

    save_state(new_state)

    if not has_any_data:
        return

    header = f"📊 *TIME ETF 일일 리포트* ({today})"
    if has_major_change:
        header += " | ⚠️ *변동 감지*"
    elif not first_run:
        header += " | 전 종목 변동 없음 ✅"

    # 4개씩 나눠서 발송
    mid = len(report_parts) // 2
    part1 = header + "\n\n" + "\n\n".join(report_parts[:mid])
    part2 = "\n\n".join(report_parts[mid:])
    insight = ""
    if not first_run:
        insight = build_insight(all_diffs_by_etf)

    for cid in chat_ids:
        send_message(cid, part1)
        send_message(cid, part2)
        if insight:
            send_message(cid, insight)

    mark_sent_today()
    print(f"[{datetime.now()}] 리포트 발송 완료")


def main():
    parser = argparse.ArgumentParser(description="TIME ETF 구성종목 수량 변동 텔레그램 봇")
    parser.add_argument("--now", action="store_true", help="즉시 1회 실행")
    parser.add_argument("--get-chatid", action="store_true", help="chat_id 확인")
    parser.add_argument("--time", default=REPORT_TIME, help="알림 시간 (기본: 22:00)")
    args = parser.parse_args()

    if args.get_chatid:
        cid = get_chat_id()
        if cid:
            print(f"Chat ID: {cid}")
        else:
            print("chat_id를 찾을 수 없습니다. 봇에게 먼저 /start 메시지를 보내세요.")
        return

    if args.now:
        check_and_report()
        return

    # 스케줄 모드
    schedule.every().day.at(args.time).do(check_and_report)
    print(f"TIME ETF 봇 시작. 매일 {args.time}에 체크합니다. (Ctrl+C로 종료)")

    # 시작 시 초기 데이터 없으면 바로 수집
    state = load_state()
    if not any(k for k in state if k != "_chat_id"):
        print("초기 데이터 수집 중...")
        check_and_report()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
