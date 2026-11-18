# 한국투자증권 시간외 실시간 예제·MCP 명세 설명 수정

## 배경

2026-09-14 KRX 거래시간 개편 이후에도 시간외 실시간 예제 설명 9곳과 KIS Code Assistant MCP의 API 명세(`data.csv`) 3곳이 `시간외 단일가(16:00~18:00) 시간대에` 데이터를 확인할 수 있다고 안내합니다.

이 문구는 예전 시장 운영 시간을 현재 TR의 제공 시간처럼 읽히게 합니다. `data.csv`는 MCP 서버가 답변에 쓰는 명세라, 예제만 고치면 AI 코딩 도우미는 계속 예전 시간을 안내합니다. 이 PR은 설명을 정리하며, TR이 새 애프터마켓에 대응하는지 또는 현재도 같은 방식으로 지원되는지는 단정하지 않습니다.

## 변경

- 7개 파일의 docstring 9곳과 `data.csv`의 설명 3곳에서 고정된 과거 시간대 안내를 제거합니다. `data.csv`에는 docstring과 같은 문구를 한 줄로 넣었습니다.
- 시간외 실시간 데이터 구독 예제라는 설명으로 바꿉니다.
- KRX 시간외 단일가가 2026-09-14부터 폐지됐다는 안내와, 해당 TR의 현행 지원 여부·데이터 제공 시간은 최신 API 공지를 확인해야 한다는 안내를 추가합니다.
- 함수명, TR ID, 구독·해제 파라미터, 반환 컬럼과 실행 로직은 변경하지 않습니다.

대상 TR은 `H0STOAA0`, `H0STOUP0`, `H0STOAC0`입니다. 각 TR의 현행 지원 여부와 정확한 제공 시간은 유지보수 담당자의 확인이 필요합니다. `16:00~20:00`을 TR 제공 시간으로 새로 기재하지 않았습니다.

## 대상 파일

- `examples_llm/domestic_stock/overtime_asking_price_krx/overtime_asking_price_krx.py`
- `examples_llm/domestic_stock/overtime_asking_price_krx/chk_overtime_asking_price_krx.py`
- `examples_llm/domestic_stock/overtime_ccnl_krx/overtime_ccnl_krx.py`
- `examples_llm/domestic_stock/overtime_ccnl_krx/chk_overtime_ccnl_krx.py`
- `examples_llm/domestic_stock/overtime_exp_ccnl_krx/overtime_exp_ccnl_krx.py`
- `examples_llm/domestic_stock/overtime_exp_ccnl_krx/chk_overtime_exp_ccnl_krx.py`
- `examples_user/domestic_stock/domestic_stock_functions_ws.py` (3곳)
- `MCP/KIS Code Assistant MCP/data.csv` (3곳, 설명 열)

## 검증

- 기준 커밋: `74b0a082fa67a0be5bf53f561719c853890ed2df`
- 변경 파일 8개, 설명 변경 12곳을 확인했습니다.
- 변경한 Python 파일을 AST로 파싱해 문법을 확인했습니다.
- 모듈·함수·클래스 docstring을 제외한 AST가 수정 전후 동일함을 확인했습니다.
- `data.csv`는 Python `csv` 모듈로 수정 전후를 파싱해 행 수(335)·열 수(11)가 같고 설명 열의 셀 3개만 바뀐 것을 확인했습니다. 인코딩(UTF-8, BOM 없음)과 줄바꿈(LF)도 그대로입니다.
- `git diff --check` 통과.
- 문서만 수정했으며 API 호출, 인증, WebSocket 연결은 실행하지 않았습니다.

## 근거

- [한국투자증권: KRX 거래시간 확대 및 NXT 제도 변경 안내(9/14)](https://securities.koreainvestment.com/main/customer/notice/Notice.jsp?cmd=TF04ga000002&num=47532)
- [경북매일: 거래소도 밤 8시까지 주식 거래…14일부터 시간외 단일가 폐지](https://www.kbmaeil.com/article/20260909500701)
