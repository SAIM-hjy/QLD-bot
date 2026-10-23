"""QLD 적립식 봇 (규칙 B + 150일선). 매일 실행하면 필요한 행동이 있을 때만 텔레그램으로 알려줍니다.

규칙
  1) 새 달의 첫 거래일: 종가가 150일선 위면 BASE 전액 매수, 아래면 BEAR_BASE_FRAC 만큼만 매수.
     (안 산 금액 + EXTRA 는 예비자금으로 적립)
  2) 고점(최근 1년) 대비 -10/-20/-30/-40/-50% 구간에 처음 들어가면 예비자금의 일부를 추가 투입.
     고점 대비 -5% 이내로 회복하면 구간 기록이 초기화됨.
  3) 매도 규칙은 없음.

상태(state.json): 예비자금 잔액, 이미 발동한 구간, 마지막으로 월 적립을 처리한 달.
  봇은 "알려준 대로 매매했다"고 가정하고 상태를 갱신합니다.
  실제로 다르게 했다면 state.json 의 숫자를 직접 고쳐주세요.

환경변수: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
          ALWAYS_NOTIFY=1  -> 행동이 없는 날도 상태 메시지 전송 (기본: 행동 있는 날만)
옵션:     python dca_bot.py --dry-run  -> 전송/저장 없이 결과만 출력
"""
import json
import os
import sys
from pathlib import Path

import requests

import strategy

# ----- 규칙 설정 (만원 단위) -----
MONTHLY_DAY = 3          # 월 적립일 (1~28). 이 날짜 이후 첫 거래일에 알림
BASE = 150               # 월 정기 적립
EXTRA = 50               # 월 예비자금 적립
MA_WINDOW = 150          # 추세 판단용 이동평균 (거래일)
BEAR_BASE_FRAC = 1.0     # 하락 추세(종가 < 이동평균)에서의 정기 적립 비율
RESET_DD = -5            # 고점 대비 이 % 이내로 회복하면 구간 기록 초기화
TIERS = [(-10, 0.20), (-20, 0.30), (-30, 0.40), (-40, 0.50), (-50, 1.00)]

STATE_PATH = Path(__file__).with_name("state.json")


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"reserve": 0, "tiers_done": [], "last_month": None}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def evaluate(close, state: dict) -> tuple[str, bool]:
    """상태를 갱신하고 (메시지, 행동 여부)를 반환."""
    dd = strategy.drawdown_pct(close)
    ma = close.rolling(MA_WINDOW).mean()
    price, d, m = float(close.iloc[-1]), float(dd.iloc[-1]), float(ma.iloc[-1])
    bear = (m == m) and price < m          # NaN 이면 하락 추세 아님
    ym = close.index[-1].strftime("%Y-%m")

    if d >= RESET_DD:
        state["tiers_done"] = []

    actions: list[str] = []

    # 1) 월 적립
    if state["last_month"] != ym and close.index[-1].day >= MONTHLY_DAY:
        buy = round(BASE * (BEAR_BASE_FRAC if bear else 1.0))
        to_reserve = (BASE - buy) + EXTRA
        state["reserve"] += to_reserve
        state["last_month"] = ym
        trend = "하락 추세" if bear else "상승 추세"
        line = f"📅 {ym} 월 적립: QLD {buy:,}만원 매수"
        if bear:
            line += f" ({trend}: 종가가 {MA_WINDOW}일선 아래라 정기 매수 {int(BEAR_BASE_FRAC*100)}%만)"
        actions.append(line)
        actions.append(f"   예비자금 +{to_reserve:,}만원 적립")

    # 2) 하락 구간 추가 투입
    done = set(state["tiers_done"])
    for thr, frac in TIERS:
        if d <= thr and thr not in done and state["reserve"] > 0:
            amt = min(round(state["reserve"] * frac), state["reserve"])
            if amt <= 0:
                continue
            state["reserve"] -= amt
            done.add(thr)
            actions.append(f"🔻 고점 대비 {thr}% 구간 진입: 예비자금에서 QLD {amt:,}만원 추가 매수")
    state["tiers_done"] = sorted(done, reverse=True)

    head = "🔔 QLD 행동 알림" if actions else "ℹ️ QLD 상태"
    body = [
        head,
        f"기준일 종가 {close.index[-1].date()}  ${price:.2f}",
        f"고점 대비 {d:.1f}% / {MA_WINDOW}일선 {'아래(하락 추세)' if bear else '위(상승 추세)'}",
        "",
        *(actions if actions else ["오늘은 할 일 없음"]),
        "",
        f"💰 예비자금 잔액: {state['reserve']:,}만원",
    ]
    if actions:
        body += ["", "※ 다르게 매매했다면 state.json 의 예비자금 잔액을 직접 수정하세요."]
    return "\n".join(body), bool(actions)


def send(text: str) -> None:
    token, chat_id = os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=20,
    )
    r.raise_for_status()


def main() -> None:
    dry = "--dry-run" in sys.argv
    state = load_state()
    msg, acted = evaluate(strategy.load_close(period="2y"), state)
    print(msg)

    if dry:
        print("\n(dry-run: 전송/저장 안 함)")
        return

    if acted or os.environ.get("ALWAYS_NOTIFY") == "1":
        send(msg)          # 전송에 실패하면 예외 -> 상태를 저장하지 않으므로 다음날 다시 시도
    save_state(state)


if __name__ == "__main__":
    main()
