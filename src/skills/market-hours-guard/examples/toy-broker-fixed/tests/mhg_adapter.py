"""mhg 경계 테스트 어댑터 — 기준표 probe를 이 저장소의 함수에 연결한다."""

from toy_broker.order_router import route_order
from toy_broker.session import krx_session
from toy_broker.us_market import is_us_regular_open

PROBES = {
    "krx_session": krx_session,
    "sor_enabled": lambda at: route_order(at) == "SOR",
    "us_regular_open": is_us_regular_open,
}
