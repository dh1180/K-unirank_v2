# K-unirank 디자인 통합 및 필터 개선 점검 (2026-10-12)

## 확인한 구조
- 전역 `templates/base.html`, `static/css/app.css`, `static/css/site-design.css`
- 입결 검색 `templates/admissions/overview.html`, 점수 비교 `compare.html`
- 입결 순위 `templates/admissions/ranking.html`, 대학/모집단위 상세 및 모바일 카드 관련 공통 선택자
- 대학 순위 허브 `templates/rankings/ranking_hub.html`, VS `templates/rankings/vote.html`
- 로그인 `templates/registration/login.html`, 공통 페이지네이션 `templates/partials/pagination.html`
- 후원 `templates/support/index.html`, `static/css/support.css`

## 디자인 진단과 실제 반영
1. 기존 페이지별 CSS에서 헤더/카드/버튼/입력 컨트롤의 보더 및 반경이 서로 달랐음: `site-design.css`에 통일된 토큰과 스타일 적용.
2. 모바일에서 표/차트 구조는 이미 여러 화면에 개별 변환 로직이 있으므로 레이아웃을 강제로 바꾸지 않고 공통 서피스/타이포/포커스 처리만 수정.
3. 다수 페이지가 `base.html`을 상속함: 상단 네비게이션의 접근 가능한 이름 및 일관된 탭/링크 상태 개선.
4. 비교 화면은 자격 제한 전형도 그대로 노출했음: 전형명 기준 기본 제외 필터와 범위 옵션 추가. 전형 자격의 법적·실질적 판정이 아닌 검색 편의 필터라는 안내 유지.
5. 후원 화면은 대학을 직접 찾아 선택하기 어려웠음: 가나다순 정렬 + 검색어에 맞춰 선택 목록 필터링하는 보조 검색 UI 구현. JS 비활성화 시 native select 기능 유지.

## 공통 설계 원칙
- 컨텐츠/입결 원본·숫자·VS Glicko-2 등 비즈니스 로직은 기존 유지
- `--brand`, `--line`, `--radius`, `--shadow-card`, `--control-radius` 등 공통 디자인 값 사용
- 모바일 720px 아래에서 레이아웃 파손을 피하고 터치 목표 42px 이상 보장
- 포커스 링/스크린리더 상태 텍스트, 감소된 모션 설정 고려
- 페이지별 강한 레이아웃 규칙(차트 좌표, 표 열 너비, 입결 지표 색상)을 덮어쓰지 않음

## 배포 후 수동 브라우저 점검 필요
- PC 1440/1024/768, 모바일 390/360, Safari/Chrome
- 입결 홈의 검색·필터/광고/부분 갱신, 비교 차트·표·60건 페이지네이션
- 후원 계좌 표시 여부는 `SUPPORT_ACCEPTING_TRANSFERS` 환경변수에 좌우됨. 실제 송금 시험은 예금주 확인 뒤 수행
- 대학목록·상세, 입결 순위, 선호도 순위, 공시 순위, VS, 로그인, 마이페이지, 후원 페이지의 헤더/카드/버튼/폼
- 키보드 탭/포커스, 브라우저 뒤로가기, 모바일 스크롤과 링크 터치
- 실제 화면 스크린샷 기반의 최종 시각 QA는 별도 진행 필요

## 테스트
- `python manage.py test admissions.test_discovery support.tests`
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `cd tests/frontend && npm ci && npm test`
