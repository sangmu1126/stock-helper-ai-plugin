from __future__ import annotations

import time
from typing import Any

from models import MarketDataProvider, MarketQuote


def float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class YFinanceMarketDataProvider:
    name = "yfinance"

    def get_quote(self, symbol: str, *, lookback_days: int = 20) -> MarketQuote:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "yfinance is not installed. Install it with `pip install yfinance` "
                "or run without --with-market-data."
            ) from exc

        now = int(time.time())
        try:
            ticker = yf.Ticker(symbol)
            fast_info = ticker.fast_info
            info = getattr(ticker, "info", {}) or {}
            recent_high, moving_average = _history_indicators(ticker, lookback_days=lookback_days)
        except Exception as exc:  # noqa: BLE001 - provider failures must become safe STOP data
            return MarketQuote(
                provider=self.name,
                symbol=symbol,
                currency=None,
                regular_market_price=None,
                previous_close=None,
                open_price=None,
                day_high=None,
                day_low=None,
                recent_high=None,
                moving_average=None,
                move_percent=None,
                market_state="UNKNOWN",
                timestamp=now,
                age_seconds=0,
                health={
                    "ok": False,
                    "source": "Yahoo Finance via yfinance",
                    "errors": ["PROVIDER_REQUEST_FAILED"],
                    "detail": str(exc),
                },
            )

        last_ts = info.get("regularMarketTime") or now
        price = float_or_none(getattr(fast_info, "last_price", None))
        previous_close = float_or_none(getattr(fast_info, "previous_close", None))
        open_price = float_or_none(getattr(fast_info, "open", None))
        day_high = float_or_none(getattr(fast_info, "day_high", None))
        day_low = float_or_none(getattr(fast_info, "day_low", None))
        currency = getattr(fast_info, "currency", None) or info.get("currency")
        market_state = str(info.get("marketState") or "UNKNOWN")
        move_percent = None
        if price is not None and previous_close not in (None, 0):
            move_percent = ((price - previous_close) / previous_close) * 100

        health = {
            "ok": price is not None and previous_close is not None,
            "source": "Yahoo Finance via yfinance",
            "errors": [],
        }
        if price is None:
            health["errors"].append("MISSING_REGULAR_MARKET_PRICE")
        if previous_close is None:
            health["errors"].append("MISSING_PREVIOUS_CLOSE")

        return MarketQuote(
            provider=self.name,
            symbol=symbol,
            currency=currency,
            regular_market_price=price,
            previous_close=previous_close,
            open_price=open_price,
            day_high=day_high,
            day_low=day_low,
            recent_high=recent_high,
            moving_average=moving_average,
            move_percent=None if move_percent is None else round(move_percent, 4),
            market_state=market_state,
            timestamp=int(last_ts),
            age_seconds=max(0, now - int(last_ts)),
            health=health,
        )

    def get_history(self, symbol: str, period: str, interval: str) -> dict[str, Any]:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "yfinance is not installed. Install it with `pip install yfinance` "
                "or run without --backtest."
            ) from exc

        try:
            frame = yf.Ticker(symbol).history(
                period=period,
                interval=interval,
                auto_adjust=False,
            )
        except Exception as exc:  # noqa: BLE001 - provider failures must become safe STOP data
            return {
                "provider": self.name,
                "symbol": symbol,
                "period": period,
                "interval": interval,
                "bars": [],
                "health": {
                    "ok": False,
                    "source": "Yahoo Finance via yfinance",
                    "errors": ["HISTORY_PROVIDER_REQUEST_FAILED"],
                    "detail": str(exc),
                },
            }

        bars: list[dict[str, Any]] = []
        previous_close: float | None = None
        if frame is not None and not frame.empty:
            for index, row in frame.iterrows():
                close = float_or_none(row.get("Close"))
                move_percent = None
                if close is not None and previous_close not in (None, 0):
                    move_percent = ((close - previous_close) / previous_close) * 100
                bars.append(
                    {
                        "date": str(index.date() if hasattr(index, "date") else index),
                        "open": float_or_none(row.get("Open")),
                        "high": float_or_none(row.get("High")),
                        "low": float_or_none(row.get("Low")),
                        "close": close,
                        "volume": float_or_none(row.get("Volume")),
                        "previous_close": previous_close,
                        "move_percent": None if move_percent is None else round(move_percent, 4),
                    }
                )
                if close is not None:
                    previous_close = close

        return {
            "provider": self.name,
            "symbol": symbol,
            "period": period,
            "interval": interval,
            "bars": bars,
            "health": {
                "ok": bool(bars),
                "source": "Yahoo Finance via yfinance",
                "errors": [] if bars else ["NO_HISTORY_BARS"],
            },
        }


class KakaoPaySecuritiesMarketDataProvider:
    name = "kakaopay-securities"

    def get_quote(self, symbol: str, *, lookback_days: int = 20) -> MarketQuote:
        now = int(time.time())
        return MarketQuote(
            provider=self.name,
            symbol=symbol,
            currency="KRW",
            regular_market_price=None,
            previous_close=None,
            open_price=None,
            day_high=None,
            day_low=None,
            recent_high=None,
            moving_average=None,
            move_percent=None,
            market_state="UNKNOWN",
            timestamp=now,
            age_seconds=0,
            health={
                "ok": False,
                "source": "KakaoPay Securities adapter stub",
                "errors": ["KAKAOPAY_SECURITIES_API_NOT_CONNECTED"],
                "detail": "공개 카카오페이증권 시세 API가 확인되지 않아 현재는 교체용 adapter contract만 제공합니다.",
            },
        )

    def get_history(self, symbol: str, period: str, interval: str) -> dict[str, Any]:
        return {
            "provider": self.name,
            "symbol": symbol,
            "period": period,
            "interval": interval,
            "bars": [],
            "health": {
                "ok": False,
                "source": "KakaoPay Securities adapter stub",
                "errors": ["KAKAOPAY_SECURITIES_API_NOT_CONNECTED"],
                "detail": "공개 카카오페이증권 과거 시세 API가 확인되지 않아 현재는 교체용 adapter contract만 제공합니다.",
            },
        }


class DemoFixtureMarketDataProvider:
    name = "demo-fixture"

    def get_quote(self, symbol: str, *, lookback_days: int = 20) -> MarketQuote:
        now = int(time.time())
        closes = _demo_closes()
        recent = closes[-lookback_days:] if lookback_days > 0 else closes[-20:]
        recent_high = max(recent) * 1.01
        moving_average = sum(recent) / len(recent)
        price = float(closes[-1])
        previous_close = float(closes[-2])
        move_percent = ((price - previous_close) / previous_close) * 100
        return MarketQuote(
            provider=self.name,
            symbol=symbol,
            currency="KRW",
            regular_market_price=price,
            previous_close=previous_close,
            open_price=previous_close,
            day_high=recent_high,
            day_low=min(recent) * 0.99,
            recent_high=recent_high,
            moving_average=moving_average,
            move_percent=round(move_percent, 4),
            market_state="OPEN",
            timestamp=now,
            age_seconds=0,
            health={
                "ok": True,
                "source": "Built-in demo fixture, not live market data",
                "errors": [],
                "demo": True,
            },
        )

    def get_history(self, symbol: str, period: str, interval: str) -> dict[str, Any]:
        closes = _demo_closes()
        bars: list[dict[str, Any]] = []
        previous_close: float | None = None
        for idx, close in enumerate(closes, start=1):
            move_percent = None
            if previous_close not in (None, 0):
                move_percent = ((close - previous_close) / previous_close) * 100
            bars.append(
                {
                    "date": f"DEMO-2026-01-{idx:02d}",
                    "open": previous_close or close,
                    "high": max(previous_close or close, close) * 1.01,
                    "low": min(previous_close or close, close) * 0.99,
                    "close": float(close),
                    "volume": 1000000 + idx,
                    "previous_close": previous_close,
                    "move_percent": None if move_percent is None else round(move_percent, 4),
                }
            )
            previous_close = float(close)

        return {
            "provider": self.name,
            "symbol": symbol,
            "period": period,
            "interval": interval,
            "bars": bars,
            "health": {
                "ok": True,
                "source": "Built-in demo fixture, not live market data",
                "errors": [],
                "demo": True,
            },
        }


def get_provider(name: str) -> MarketDataProvider:
    if name == "demo-fixture":
        return DemoFixtureMarketDataProvider()
    if name == "yfinance":
        return YFinanceMarketDataProvider()
    if name == "kakaopay-securities":
        return KakaoPaySecuritiesMarketDataProvider()
    raise ValueError(f"Unsupported market data provider: {name}")


def _history_indicators(ticker: Any, *, lookback_days: int = 20) -> tuple[float | None, float | None]:
    try:
        frame = ticker.history(period="1mo", interval="1d", auto_adjust=False)
    except Exception:  # noqa: BLE001
        return None, None
    if frame is None or frame.empty:
        return None, None
    closes = [float_or_none(value) for value in frame.get("Close", [])]
    highs = [float_or_none(value) for value in frame.get("High", [])]
    closes = [value for value in closes if value is not None]
    highs = [value for value in highs if value is not None]
    recent_closes = closes[-lookback_days:]
    recent_highs = highs[-lookback_days:]
    recent_high = max(recent_highs) if recent_highs else None
    moving_average = sum(recent_closes) / len(recent_closes) if recent_closes else None
    return recent_high, moving_average


def _demo_closes() -> list[int]:
    return [
        100000,
        97000,
        94000,
        91000,
        88000,
        77000,
        83000,
        80000,
        76000,
        82000,
        79000,
        75000,
        72000,
        78000,
        74000,
        70000,
        76000,
        73000,
        69000,
        75000,
        71000,
        68000,
        74000,
        70000,
        67000,
        73000,
        69000,
        66000,
        72000,
        68000,
    ]
