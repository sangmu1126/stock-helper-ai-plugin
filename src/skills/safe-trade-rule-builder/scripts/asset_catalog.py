"""오프라인 파서가 인식하는 종목 목록.

LLM 파서를 쓸 수 없는 환경(API 키 없음, 심사·데모)에서도 자주 쓰는 국내·미국 종목을 인식하게 한다.
목록에 없는 종목은 6자리 종목코드(국내)나 대문자 티커(미국)로 입력하면 된다.
시장은 심볼로 구분한다: .KS(코스피)·.KQ(코스닥)는 KRX, 접미사가 없으면 미국.
"""

from __future__ import annotations

import re

# (심볼, 영문 이름, 한글·별칭 목록)
KRX_ASSETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("005930.KS", "Samsung Electronics", ("삼성전자",)),
    ("000660.KS", "SK hynix", ("SK하이닉스", "하이닉스")),
    ("373220.KS", "LG Energy Solution", ("LG에너지솔루션", "엘지에너지솔루션", "LG엔솔")),
    ("207940.KS", "Samsung Biologics", ("삼성바이오로직스",)),
    ("005380.KS", "Hyundai Motor", ("현대차", "현대자동차")),
    ("000270.KS", "Kia", ("기아",)),
    ("068270.KS", "Celltrion", ("셀트리온",)),
    ("035420.KS", "NAVER", ("네이버", "NAVER")),
    ("035720.KS", "Kakao Corp", ("카카오",)),
    ("323410.KS", "KakaoBank", ("카카오뱅크",)),
    ("377300.KS", "Kakao Pay", ("카카오페이",)),
    ("005490.KS", "POSCO Holdings", ("POSCO홀딩스", "포스코홀딩스")),
    ("051910.KS", "LG Chem", ("LG화학", "엘지화학")),
    ("006400.KS", "Samsung SDI", ("삼성SDI",)),
    ("105560.KS", "KB Financial Group", ("KB금융",)),
    ("055550.KS", "Shinhan Financial Group", ("신한지주",)),
    ("012450.KS", "Hanwha Aerospace", ("한화에어로스페이스",)),
    ("329180.KS", "HD Hyundai Heavy Industries", ("HD현대중공업",)),
    ("086520.KQ", "EcoPro", ("에코프로",)),
    ("247540.KQ", "EcoPro BM", ("에코프로비엠",)),
    ("196170.KQ", "Alteogen", ("알테오젠",)),
    ("069500.KS", "KODEX 200", ("KODEX 200", "KODEX200")),
    ("360750.KS", "TIGER US S&P500", ("TIGER 미국S&P500", "TIGER미국S&P500")),
)

US_ASSETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("TSLA", "Tesla", ("테슬라",)),
    ("AAPL", "Apple", ("애플",)),
    ("NVDA", "NVIDIA", ("엔비디아",)),
    ("MSFT", "Microsoft", ("마이크로소프트",)),
    ("AMZN", "Amazon", ("아마존",)),
    ("GOOGL", "Alphabet", ("구글", "알파벳")),
    ("META", "Meta Platforms", ("메타플랫폼스", "메타")),
    ("NFLX", "Netflix", ("넷플릭스",)),
    ("PLTR", "Palantir", ("팔란티어",)),
    ("AVGO", "Broadcom", ("브로드컴",)),
    ("AMD", "AMD", ()),
    ("QQQ", "Invesco QQQ Trust", ()),
    ("SPY", "SPDR S&P 500 ETF", ()),
    ("TQQQ", "ProShares UltraPro QQQ (3x)", ()),
    ("SOXL", "Direxion Daily Semiconductor Bull 3x", ()),
)

_ALL = KRX_ASSETS + US_ASSETS
_BY_CODE = {symbol.split(".")[0]: (symbol, name) for symbol, name, _ in KRX_ASSETS}
_US_TICKERS = {symbol: name for symbol, name, _ in US_ASSETS}
# 긴 별칭부터 비교해 '카카오뱅크'가 '카카오'로, '에코프로비엠'이 '에코프로'로 잡히지 않게 한다.
_ALIASES = sorted(
    ((alias.upper(), symbol, name) for symbol, name, aliases in _ALL for alias in aliases),
    key=lambda item: -len(item[0]),
)
# 6자리 숫자라도 '100000원만', '100000주'처럼 금액·수량이면 종목코드가 아니다.
_CODE_RE = re.compile(r"(?<![\d,])(\d{6})(?:\.(KS|KQ))?(?![\d,])(?!\s*(?:원|주|%|만))")
_TICKER_RE = re.compile(r"(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])")


def find_asset(text: str) -> dict[str, str] | None:
    """문장에서 종목을 찾는다. 6자리 코드 → 한글·별칭(긴 것 우선) → 미국 대문자 티커 순."""
    code = _CODE_RE.search(text)
    if code:
        known = _BY_CODE.get(code.group(1))
        if known:
            return {"symbol": known[0], "name": known[1]}
        suffix = code.group(2) or "KS"
        symbol = f"{code.group(1)}.{suffix}"
        return {"symbol": symbol, "name": symbol}
    upper = text.upper()
    for alias, symbol, name in _ALIASES:
        if alias in upper:
            return {"symbol": symbol, "name": name}
    for match in _TICKER_RE.finditer(text):
        if match.group(1) in _US_TICKERS:
            return {"symbol": match.group(1), "name": _US_TICKERS[match.group(1)]}
    return None


def symbol_aliases() -> dict[str, str]:
    """LLM 출력 정규화용 별칭(소문자 키) → 심볼."""
    table: dict[str, str] = {}
    for symbol, name, aliases in _ALL:
        for key in (symbol, name, *aliases):
            table[key.lower()] = symbol
    for code, (symbol, _name) in _BY_CODE.items():  # 시장 접미사를 잘못 붙인 출력도 바로잡는다
        for key in (code, f"{code}.ks", f"{code}.kq"):
            table[key] = symbol
    return table
