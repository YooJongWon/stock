# 포트폴리오 저장 설정

## 1. 기존 Supabase 프로젝트 사용

Supabase Dashboard의 SQL Editor에서 `supabase/portfolio.sql` 내용을 한 번 실행합니다. 이 작업은 기존 프로젝트에 `private_portfolio_data` 테이블 하나만 추가합니다.

## 2. Vercel 환경변수

Vercel 프로젝트의 Settings → Environment Variables에 아래 값을 등록하고 Production 배포를 다시 진행합니다.

- `SUPABASE_URL`: Supabase Project URL
- `SUPABASE_SECRET_KEY`: Supabase Settings → API Keys → Secret keys의 `sb_secret_...` 키 (권장)
- 또는 구형 키를 사용하는 경우 `SUPABASE_SERVICE_ROLE_KEY`: Legacy API Keys의 `service_role` 키
- `PORTFOLIO_ACCESS_PASSWORD`: 포트폴리오 탭을 열 때 사용할 본인만 아는 비밀번호
- `PORTFOLIO_SESSION_SECRET`: 32자 이상의 임의 비밀 문자열

Secret key (`sb_secret_...`) 또는 구형 `service_role` 키는 절대 `NEXT_PUBLIC_` 접두사를 붙이지 말고 브라우저 코드나 Git 저장소에 기록하지 마세요. 새 Secret key는 `apikey` 헤더로만 전송하고, 구형 service_role JWT는 `Authorization: Bearer` 헤더도 함께 사용하도록 서버 코드가 구분합니다. 이 앱은 모든 DB 요청을 Next.js 서버에서 처리합니다.

## 3. 사용 방법

사이트에서 포트폴리오 탭을 열고 `PORTFOLIO_ACCESS_PASSWORD`로 인증합니다. 인증 세션은 HttpOnly 쿠키로 7일간 유지됩니다.

예수금은 USD로 입력하고, 보유 종목은 티커·실제 매수금액·선택 메모와 매매 진행 단계를 관리합니다. 변경사항은 자동 저장됩니다. 계산기 설정도 인증된 상태에서 Supabase에 자동 저장됩니다. 보유 종목·예수금·계산기 설정은 동일한 Supabase 행에 별도 필드로 저장되므로 서로 덮어쓰지 않습니다.

시세 및 증권사 계좌 연동은 포함하지 않았으며 종목별 수량·평균 매수가·현재가는 저장하지 않습니다.

## 계산기에서 종목별 매수가 제거

계산기는 총투자금, 종목 수, 현금·매수 비중과 손절·익절 수익률만 저장합니다. 종목별 1주당 매수가(`firstEntryPrice`)는 사용하지 않습니다.

DB 스키마 변경이나 필수 SQL 마이그레이션은 없습니다. 설정은 `calculator_settings` JSONB에 저장되며, 기존 JSON에 남은 `firstEntryPrice`는 새 화면에서 무시됩니다. 다음 계산기 자동 저장 시 서버가 지원하는 키만 저장하므로 해당 키도 자연스럽게 제거됩니다. 기존 총투자금·전략 설정·예수금·보유 종목은 유지됩니다. 구버전 클라이언트가 해당 키를 보내더라도 서버는 이를 무시합니다.

## 2단계 익절 기준으로 전환

운용 기본값은 손절 -5%, 익절 +6%에 최초 수량의 50%, +10%에 남은 전량입니다. 계산기와 포트폴리오의 매매 기록에 `exitPlanVersion: "2"`를 저장합니다. 2차 매수는 확인 가능한 날에만 수동으로 판단하며, 1차 매수만 완료된 종목도 익절을 기록할 수 있습니다. 마지막 익절 또는 손절 기록을 확정하면 종목이 삭제됩니다.

필수 SQL 마이그레이션은 없습니다. 기존 계산기 설정은 조회 시 새 기본 익절·손절 기준으로 전환하고, 총투자금·종목 수·현금 및 매수 비중은 보존합니다. 버전 2 이후 고급 설정 변경은 유지됩니다.

기존 40/30/30 매도 이력은 실제 매도 비중을 보존합니다. 1차까지 매도했다면 `legacySoldPct: 40`으로 남은 60%, 2차까지 매도했다면 `legacySoldPct: 70`으로 남은 30%를 마지막 +10% 익절에서 정리합니다. 완료 종목을 임의로 다시 활성화하지 않으며 되돌리기 스냅샷도 같은 방식으로 전환합니다. 기존 체결의 수익률을 새 +6%로 추정해 표시하지 않습니다. 조회 결과는 다음 자동 저장 때 JSONB에 반영됩니다.

검증 명령: `cd web && npm run test:strategy`

## 토스 매수 상태 동기화

Supabase SQL Editor에서 `supabase/toss-buy-stages.sql`을 한 번 실행합니다. 기존 포트폴리오와 같은 서버 환경 변수 및 접근 세션을 사용합니다. 기존 브라우저에 저장된 상태는 토스 탭을 열면 가져옵니다. 서버에 저장된 값이 있으면 그 값을 유지합니다.
