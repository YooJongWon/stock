# 포트폴리오 저장 설정

## 1. 기존 Supabase 프로젝트 사용

Supabase Dashboard의 SQL Editor에서 `supabase/portfolio.sql` 내용을 한 번 실행합니다. 이 작업은 기존 프로젝트에 `private_portfolio_data` 테이블 하나만 추가합니다.

## 2. Vercel 환경변수

Vercel 프로젝트의 Settings → Environment Variables에 아래 값을 등록하고 Production 배포를 다시 진행합니다.

- `SUPABASE_URL`: Supabase Project URL
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase의 서버 전용 service_role 키
- `PORTFOLIO_ACCESS_PASSWORD`: 포트폴리오 탭을 열 때 사용할 본인만 아는 비밀번호
- `PORTFOLIO_SESSION_SECRET`: 32자 이상의 임의 비밀 문자열

service_role 키는 절대 `NEXT_PUBLIC_` 접두사를 붙이지 말고 브라우저 코드나 Git 저장소에 기록하지 마세요. 이 앱은 모든 DB 요청을 Next.js 서버에서 처리합니다.

## 3. 사용 방법

사이트에서 포트폴리오 탭을 열고 `PORTFOLIO_ACCESS_PASSWORD`로 인증합니다. 인증 세션은 HttpOnly 쿠키로 7일간 유지됩니다.

예수금은 USD로 직접 입력하고, 보유 종목은 티커·회사명·수량·평균 매수가·현재가를 직접 입력합니다. 계산기 설정도 인증된 상태에서 Supabase에 자동 저장됩니다. 보유 종목·예수금·계산기 설정은 동일한 Supabase 행에 별도 필드로 저장되므로 서로 덮어쓰지 않습니다.

시세 및 증권사 계좌 연동은 포함하지 않았습니다. 현재가는 사용자가 직접 갱신해야 합니다.
