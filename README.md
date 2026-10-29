# 미국주식 스윙 스크리너

Python이 미국 보통주를 일봉으로 분석해 매수(BUY), 관심(WATCH), 제외(REJECT)를 판정합니다. Finviz는 독립 검산에만 쓸 수 있고 프로그램 의존성이나 스크래핑은 없습니다. TradingView Pine은 차트 보조 지표이며 재무조건까지 판정하는 최종 엔진은 Python입니다.

## 실행

Python 3.11 이상을 사용합니다. SEC 요청용 식별자는 `.env`의 `SEC_USER_AGENT`에 앱 이름과 연락 가능한 이메일을 설정합니다. 실제 연락처는 저장소에 기록하지 마세요.

```powershell
cd C:\my\hobby\stock
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe main.py --limit 10
.\.venv\Scripts\python.exe main.py --ticker AAPL
.\.venv\Scripts\python.exe -m pytest
```

첫 전체 실행은 수천 종목의 가격 자료를 요청하므로 오래 걸릴 수 있습니다. 기준일은 미국 동부시간 기준 가장 최근에 정규장이 끝난 NYSE 세션이며, 종목 데이터와 SPY에 같은 날짜를 사용합니다. `--reference-date YYYY-MM-DD`는 재현 가능한 과거 분석용입니다.

## 판정 규칙

### 재무·유동성 필터

- 시가총액 20억 달러 이상, 주가 10달러 이상
- 30거래일 평균 거래량 100만 주 이상 및 평균 거래대금 3,000만 달러 이상
- 0 < P/E < 40, ROE 15% 초과, 5년 매출 CAGR 5% 초과
- 재무 데이터는 SEC EDGAR XBRL 우선, Yahoo Finance 보조 순서입니다. SEC의 각 재무 사실은 `filing_date <= reference_date`인 자료만 사용합니다. Yahoo 재무 스냅샷은 공시일을 증명할 수 없으면 과거 기준일에 적용하지 않습니다. 이 경우 재무 미확인으로 BUY가 되지 않습니다.

### 기술 필터 및 점수

- 상승 추세: EMA20 > SMA50 > SMA200, SMA50 > SMA50[5]
- 시장 환경: SPY 종가 > SMA200, SMA50 > SMA200, SMA50 > SMA50[5]가 모두 참이면 상승장입니다. 그 외에는 위험구간 경고를 표시하지만, 시장 환경 하나만으로 BUY를 차단하지는 않습니다. 나머지 재무·유동성·기술 필터는 그대로 모두 통과해야 합니다.
- 상대강도: 종목 63거래일 ROC - SPY 63거래일 ROC > 0
- RSI14: 55 이상 68 미만
- 눌림: 최근 3봉 중 `Low <= SMA50 + 0.25*ATR14` 이면서 `Close >= SMA50 - 0.25*ATR14`인 봉이 있고, 현재 종가가 SMA50 - 0.25*ATR14 아래로 무너지지 않을 것
- 거래량 감소: 최근 3봉 중 거래량이 20일 평균의 90% 미만인 봉이 있을 것
- 거래량 증가: 기준봉 거래량이 20일 평균의 110% 초과
- 강한 양봉: 종가 > 시가, 몸통/전체 범위 >= 0.40, 종가 위치 >= 0.60, 종가 > 전일 고가
- SMA50 이격: 0~2 ATR
- 초기 손절: 종가 기준 진입 추정가 - 1.5*ATR14. 손절 위험은 5% 이하여야 하며 5% 초과를 잘라 맞추지 않습니다.
- 1R은 진입 추정가-초기 손절, 2R 목표는 진입 추정가+2R입니다. +1R에서 본전, +1.5R 이후 `EMA10 - 0.5*ATR14` 추적손절을 계획하며 최대 보유기간은 20거래일입니다.

10점 점수는 추세 배열 +2, SMA50 상승 +1, 상대강도 양수 +2, 최근 눌림 +2, 강한 양봉 +1, 거래량 증가 +1, RSI 구간 +1입니다. BUY는 위의 재무·유동성·기술 조건을 모두 통과하고 점수 7점 이상이어야 합니다. 시장 환경은 별도 위험 경고이며 BUY의 차단 조건은 아닙니다. WATCH는 재무 조건이 확인되고 상승 추세가 유지되며 점수 6점 이상이지만 BUY 조건 일부가 부족한 경우입니다. 그 외는 REJECT이고 미충족 사유를 결과에 기록합니다.

`Entry Plan`, 손절 및 목표는 기준봉 종가로 계산한 추정 가격입니다. 실제 계획은 다음 거래일 시가 진입을 전제로 하며 갭이 생기면 가격과 위험도가 달라집니다.

## 출력 파일

- `output/all_screened.csv`: 분석한 전체 종목과 측정값, 판정 사유
- `output/final_candidates.csv`: BUY와 WATCH, BUY 우선 정렬
- `output/rejected.csv`: REJECT 목록
- `output/run_summary.json`: 시장환경, 스캔 수, 재무 조회 수, 실행 시간 등
- `output/final_candidates.md`: 매수·관심 결과를 한글로 읽기 쉽게 정리
- `output/technical_candidates.md` 및 `.csv`: 기술 후보 목록

BUY 정렬은 점수, SPY 대비 상대강도, ATR 손절률 낮은 순, RSI 60~65 근접도, 시가총액 순입니다.

## Finviz 및 TradingView

Finviz는 빠른 후보 검산에만 사용합니다. 참고 조건은 USA, 시가총액 Mid 이상, 가격 10달러 초과, 평균 거래량 1M 초과, P/E 40 미만, ROE 15% 초과, 5년 매출 성장 5% 초과, SMA20/SMA50 위, SMA50>SMA200입니다. Finviz 결과를 가져오거나 Python BUY를 대체하지 않습니다.

`TradingView_US_Swing_v4_2.pine`은 Pine v6 `indicator()`이며 `strategy()` 주문이나 백테스트를 사용하지 않습니다. 차트의 추세·눌림·거래량·상대강도·RSI·ATR·신호·손절·2R·보유 상태를 표시합니다. Pine은 기업별 SEC point-in-time 재무 검증을 Python과 동일하게 제공할 수 없으므로 Pine의 “기술적 매수”는 최종 Python BUY와 동의어가 아닙니다. 알림은 기술 조건 참고용이고, 최종 재무 필터 통과 여부는 Python 결과를 확인해야 합니다.

## 데이터 한계 및 위험

가격은 yfinance 우선, Stooq 대체로 가져옵니다. yfinance는 최대 3회 재시도(1, 2, 4초 대기) 후 실패 시 Stooq를 사용합니다. 데이터 누락·오류 종목은 DATA_ERROR로 기록하고 전체 실행을 계속합니다. 지연 OHLCV는 최대 7일만 허용합니다. yfinance 조정주가와 Stooq 가격 조정 방식, TradingView 제공 데이터에는 차이가 있을 수 있습니다. SEC는 API 키나 계정 신청이 필요 없지만 식별 가능한 User-Agent와 공정 이용 속도 제한을 지켜야 합니다.

SEC에 상장사 CIK가 없는 교환 디렉터리 티커는 SEC 재무조회가 불가능할 수 있으며 Yahoo의 공시일 없는 스냅샷은 look-ahead 방지를 위해 과거 기준일에서 제외됩니다. 시장데이터 서비스의 오류·지연·상장폐지 심볼 등으로 개별 종목은 분석에서 빠질 수 있습니다.

BUY는 명시된 정량 조건을 만족했다는 뜻이지 수익을 보장하지 않습니다. 뉴스, 실적 발표, 갭, 거래정지, 유동성 급변, 시장 레짐 변화 등 비정량 위험을 확인하고 실제 주문은 사용자가 결정해야 합니다.

## GitHub Actions 및 웹 대시보드

### 로컬 검증

```powershell
.\.venv\Scripts\python.exe -m pytest
```

웹 앱은 `web/`에 있습니다. Node.js 20.9 이상과 npm을 설치한 뒤 다음처럼 실행합니다.

```powershell
cd web
npm ci
npm run dev
```

### 비공개 GitHub 저장소 연결

1. GitHub에서 빈 비공개 저장소를 만듭니다. README, `.gitignore`, 라이선스는 GitHub에서 생성하지 않습니다.
2. 이 프로젝트의 기본 브랜치를 저장소에 push합니다.
3. 저장소의 **Settings → Secrets and variables → Actions**에서 `SEC_USER_AGENT` secret을 추가합니다. 앱 이름과 실제 연락 가능한 이메일을 사용하되 코드나 문서에는 적지 않습니다.
4. **Actions**에서 워크플로를 활성화하고 **US stock screener → Run workflow**를 한 번 실행합니다.

자동 스케줄은 한국 시간 오전 9시(UTC 00:00, 화~토)입니다. 한국 날짜 기준 전날이 XNYS 거래일일 때만 스크리너를 호출하고, 미국 휴장일은 건너뜁니다. SPY와 각 종목 봉이 기준일 종가까지 갱신되지 않은 경우 stale 종목을 DATA_ERROR로 기록하고, SPY가 기준일 종가가 아니면 새 결과를 게시하지 않습니다. 실패 상태는 별도 JSON에 남기며 이전 정상 결과 JSON/CSV를 유지합니다.

정상 후보 CSV와 대시보드 JSON 및 `final_candidates.md`는 `web/public/data/`에 저장되고 Actions가 변경된 파일만 커밋합니다. 웹은 기존 `output/final_candidates.md`와 동일한 스크리너 보고서를 표시하고 실행 한국 시간과 조회한 미국 거래일을 상단에 보여줍니다. 워크플로에는 `push` 트리거가 없으므로 이 커밋이 스크리너를 다시 실행하지 않습니다.

### 새 Vercel 프로젝트 연결

1. Vercel에서 기존 프로젝트를 선택하지 말고 **New Project**로 이 비공개 GitHub 저장소를 연결합니다.
2. Root Directory를 `web`로 설정하고 Next.js 기본 빌드 설정을 사용합니다.
3. Python 또는 SEC API secret은 Vercel에 넣지 않습니다. 대시보드는 공개 결과 JSON/CSV만 읽습니다.
4. 첫 Actions 실행의 데이터 커밋 뒤 Vercel 배포에서 Markdown 후보 리포트와 CSV 다운로드를 확인합니다.

비공개 저장소 연결과 별개로 Vercel Hobby로 배포한 사이트와 JSON/CSV URL은 공개됩니다. 페이지 검색 색인은 비활성화했지만 URL 접근을 막지는 않으므로, 공개해도 되는 종목 및 지표만 저장소에 게시해야 합니다. 개인 정보와 API 키는 게시하지 않습니다.

스케줄된 워크플로 실행은 전날 XNYS 거래일이 없거나 마지막 XNYS 기준일이 이미 게시된 날짜와 같으면 건너뜁니다. 수동 실행은 같은 세션도 다시 계산합니다.
