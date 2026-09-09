# K-unirank 프로젝트 인수인계

> 기준일: 2026-09-09  
> 이 문서는 긴 대화가 종료되어도 다음 작업에서 현재 상태를 바로 이어갈 수 있도록 정리한 운영 메모입니다. 실제 동작 기준은 항상 GitHub `main`의 최신 코드를 우선합니다.

## 1. 서비스 핵심 경로

- `/` — 대학·학과 입결 찾기
- `/admissions/compare/` — 내 점수로 학과 찾기
- `/admissions/ranking/` — 입결 순위
- `/vs/` — 대학 VS 투표
- `/ranking/` — 사용자 선호도 순위
- `/rankings/` — 통합 순위 허브
- `/universities/` — 대학 찾기
- `/universities/indicators/<metric>/` — 대학알리미 공식 지표 순위

## 2. 내 점수로 학과 찾기

`admissions/compare_views.py` + `templates/admissions/compare.html`로 구현되어 있습니다.

현재 기능:

- 4년제 수시 공식 입결 대상
- 내신 평균등급 `1.0~9.0` 입력
- 학생부교과 / 학생부종합 선택
- 학년도 선택
- 지역 필터
- 학과 검색, 쉼표로 여러 검색어 입력 가능
- `내 등급 ±0.5` 또는 전체 보기
- `STUDENT_GRADE_70_CUT` 우선, 없으면 `STUDENT_GRADE_50_CUT`을 비교 기준으로 사용
- 대학 입학처(`UNIVERSITY`)와 어디가(`ADIGA`) 중 같은 결과가 겹치면 대학 입학처 출처 우선
- 내 등급과 컷의 차이는 `앞섬 / 컷과 비슷 / 뒤`로만 표현하며 합격 확률로 해석하지 않음
- 대학별 비교 그래프 + 모집단위 상세 표
- sitemap 등록 완료

관련 초기 구현 커밋:

- `57c71c087c3f2456f261e7b6388e29081a8b8ee1` — 비교 로직
- `182bafacf5feee58f9a6b512a75fd43dbeb41ce1` — 비교 화면
- `68437762b0a401a2eab66ad388bad75dcd1da1b6` — 라우트
- `831a41c5f6a17e33132a455cc7cb86c143fc86a0` — sitemap

## 3. 수시 수능최저 데이터

### 데이터 구조

수능최저는 과거 입시결과와 성격이 달라 `AdmissionResult`에 섞지 않고 `AdmissionRequirement`에 별도로 저장합니다.

- `requirement_type = CSAT_MINIMUM`
- 실제 모집학년도 보존
- 출처: ADIGA Q1 `전형별 주요사항`
- source code / source URL 저장
- 전형명 또는 모집단위 범위 저장

### 최신 학년도 fallback

`python manage.py sync_adiga_csat_minimum --year 2027`

대학별 동작:

1. 2027 Q1에서 안전한 수능최저 규칙 확인
2. 있으면 2027 자료 사용
3. 없으면 2026 Q1을 한 번 확인
4. 2026 자료가 있으면 **2026으로 저장**
5. 둘 다 없으면 미확인

2026 자료를 2027로 가장하지 않습니다.

### 안전 필터

현재 적용된 주요 방어:

- `tab_40` 정시/수능위주 영역 구조적으로 제외
- 전형명에 `정시`, `수능위주`, `수능 (...)`가 명확한 경우 제외
- `(가군)`, `(나군)`, `(다군)` 제외
- 서울대 정시 농어촌·저소득 미술/음악 잔여 오탐 제외
- 설명문/표 헤더를 전형명으로 오인한 행 제외
- 전형/모집단위 매칭이 애매하면 결과 행에 붙이지 않음
- 홍익대학교 서울/세종처럼 원문에 캠퍼스가 명시된 확인 사례는 현재 University 범위와 충돌하면 제외

## 4. 수능최저 검수 상태 — 중요

**아직 운영 DB에 전체 `--apply` 하지 않는 것이 현재 원칙입니다.**

2026-09-09 전체 미리보기는 Railway SSH 연결이 끝까지 유지되지 않아 마지막 통계 전에 종료되었습니다. 따라서 전체 검수 완료로 간주하면 안 됩니다.

확인된 사항:

- 이전의 명백한 정시 모집군 오탐은 크게 줄어듦
- 홍익대학교/홍익대학교 세종캠퍼스 결과에 `(서울)`과 `(세종)` 전형이 서로 교차 노출되는 문제가 발견되어 캠퍼스 범위 필터를 추가함
- 일부 fallback 대학은 현재 결과와 전형명 매칭률이 매우 낮거나 0건이므로 자동으로 결과 행에 붙이지 않는 현재 보수적 정책 유지
- `수능최저 적용` 뒤에 선발방법/지원자격 설명이 길게 붙는 공식 원문이 일부 있음. 숫자 기준이 공식 Q1에서 명확히 분리되지 않는 경우 임의로 수치를 추정하지 않음

### 다음 검수 방법

Railway SSH가 긴 실행 중 끊길 수 있으므로 `--offset`과 `--limit`으로 나눠 실행합니다.

```bash
python manage.py sync_adiga_csat_minimum --year 2027 --offset 0   --limit 60 --show-rules
python manage.py sync_adiga_csat_minimum --year 2027 --offset 60  --limit 60 --show-rules
python manage.py sync_adiga_csat_minimum --year 2027 --offset 120 --limit 60 --show-rules
python manage.py sync_adiga_csat_minimum --year 2027 --offset 180 --limit 60 --show-rules
```

각 구간에서 다음을 확인합니다.

- 정시/모집군 행 존재 여부
- 다른 캠퍼스 전형 혼입 여부
- 전형명이 지원자격/설명문으로 깨진 행
- 비정상적으로 긴 문구
- 2026 fallback 대학의 매칭률

모든 구간 확인 후에만 `--apply`를 실행합니다.

## 5. 입시 데이터 신뢰 원칙

- 공개 원문에서 확인되지 않는 숫자는 추정하지 않음
- 성적 단위가 불명확하면 임의의 등급/백분위로 바꾸지 않음
- 4년제와 전문대의 서로 다른 성적 체계를 한 지표로 섞지 않음
- 대학 입학처 공식 자료가 같은 범위의 ADIGA 결과를 대체하는 경우 공식 대학 자료를 우선
- 대학 단위 집계와 모집단위 원본 결과를 분리
- 화면의 `합격 가능성` 표현은 사용하지 않고 공식 컷과의 단순 거리만 보여줌

## 6. 대학알리미 공식 지표

`UniversityIndicator`로 다음 7개 공시 지표를 관리합니다.

- 취업률
- 평균 등록금
- 학생 1인당 장학금
- 기숙사 수용률
- 학생 1인당 교육비
- 전임교원 1인당 학생 수
- 전임교원 확보율

공식 지표 순위는 선호도 랭킹 및 입결 순위와 별개 기준으로 제공합니다.

## 7. 배포

- GitHub `main` → Railway 자동 배포
- Web 서비스는 시작 시 migration 및 collectstatic 실행 후 gunicorn 실행
- 코드 수정 후 GitHub commit status의 Railway 배포 결과를 확인할 것
- 배포 상태를 확인하지 않고 성공했다고 단정하지 말 것

## 8. 다음 작업 우선순위

1. 새 캠퍼스 필터가 반영된 수능최저 미리보기를 60개 단위로 재검수
2. 이상 행이 없으면 수능최저 `--apply`
3. 실제 대학 상세 페이지에서 2027/2026 최신 최저 표시 확인
4. 내 점수 학과 찾기 UX/모바일 화면 실사용 확인
5. 입시 집계 및 전문대 점수 단위 추정 로직의 데이터 무결성 추가 점검

## 9. 주요 파일

- `admissions/compare_views.py`
- `templates/admissions/compare.html`
- `admissions/models.py`
- `admissions/services/csat_minimum.py`
- `admissions/services/csat_minimum_quality.py`
- `admissions/management/commands/sync_adiga_csat_minimum.py`
- `admissions/university_detail_views.py`
- `admissions/test_csat_minimum_quality.py`
- `config/sitemaps.py`
