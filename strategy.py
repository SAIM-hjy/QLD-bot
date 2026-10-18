"""QLD 신호 계산 로직. 기준값은 여기서만 바꾸면 됩니다."""
import pandas as pd
import yfinance as yf

TICKER = "QLD"
HIGH_WINDOW = 252      # 고점 기준 기간 (거래일, 약 1년)
BUY_DD = -15.0         # 고점 대비 이 % 이하로 빠지면 매수 신호 (임시값)
SELL_DD = -3.0         # 고점 대비 이 % 이내로 회복하면 매도 신호 (임시값)
RSI_PERIOD = 14


def load_close(period: str = "2y") -> pd.Series:
    close = yf.Ticker(TICKER).history(period=period, auto_adjust=True)["Close"]
    close = close.dropna()
    close.index = close.index.tz_localize(None).normalize()  # 시간대 제거
    return close


def rsi(close: pd.Series, n: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def drawdown_pct(close: pd.Series, window: int = HIGH_WINDOW) -> pd.Series:
    high = close.rolling(window, min_periods=1).max()
    return (close / high - 1) * 100


def evaluate(close: pd.Series) -> dict:
    dd = drawdown_pct(close)
    r = rsi(close)
    last_dd, last_rsi = float(dd.iloc[-1]), float(r.iloc[-1])

    if last_dd <= BUY_DD:
        signal = "BUY"
    elif last_dd >= SELL_DD:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "date": close.index[-1].strftime("%Y-%m-%d"),
        "price": float(close.iloc[-1]),
        "drawdown": last_dd,
        "rsi": last_rsi,
        "signal": signal,
    }
