# K-unirank 2.0

사용자 선택으로 대학 선호도 랭킹을 만드는 Django 프로젝트입니다.

## 구현된 기능

- 대학 VS 투표와 `잘 모르겠어요` 건너뛰기
- 익명 Django 세션 기반 참여, 로그인 사용자는 세션에 계정 연결
- 원본 `ComparisonVote`는 수정하지 않고 보존
- Glicko-2 기반 대학별 파생 점수
- 종합 / 취업 / 캠퍼스 / 인지도 카테고리 랭킹
- 랭킹 일별 스냅샷과 등락 표시
- 투표 기록으로 나의 대학 TOP10 생성 및 공유 링크
- CareerNet 대학 목록 동기화
- 캠퍼스 통합 저장, 한국폴리텍대학 캠퍼스는 별도 유지
- 사내대학 제외
- 기존 SQLite 대학과 직접 정리한 로고 이전
- 대학 상세 페이지
- 입시결과 / 모집단위 / 지표 / 출처 / 대학 단위 집계 모델
- 출처 URL을 함께 저장하는 입시 CSV 가져오기
- Django 관리자
- 기본 JSON API
- Koyeb 등 컨테이너 배포를 위한 Dockerfile / DATABASE_URL 지원

## 로컬 실행

`.env.example`을 참고해 `.env`를 만듭니다.

```env
DJANGO_SECRET_KEY=로컬용랜덤문자열
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

DB_NAME=kunirank
DB_USER=kunirank
DB_PASSWORD=원하는로컬비밀번호
DB_HOST=127.0.0.1
DB_PORT=5432

CAREER_API_KEY=본인키
```

설치:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

PostgreSQL:

```powershell
docker compose up -d
```

처음 DB 생성:

```powershell
python manage.py makemigrations universities rankings admissions users
python manage.py migrate
python manage.py init_kunirank
```

기존 대학과 로고 이전:

```powershell
python manage.py migrate_legacy_universities --legacy-db legacy/db.sqlite3 --legacy-media media
```

CareerNet 미리보기:

```powershell
python manage.py sync_career_universities
```

확인 후 반영:

```powershell
python manage.py sync_career_universities --apply --create-new
```

서버:

```powershell
python manage.py runserver
```

- 메인: `http://127.0.0.1:8000/`
- VS: `http://127.0.0.1:8000/vs/`
- 랭킹: `http://127.0.0.1:8000/ranking/`
- 관리자: `http://127.0.0.1:8000/admin/`
- 상태 확인: `http://127.0.0.1:8000/health/`

관리자 계정:

```powershell
python manage.py createsuperuser
```

## 랭킹 운영 명령

현재 랭킹을 오늘 스냅샷으로 저장:

```powershell
python manage.py create_ranking_snapshot
```

원본 투표부터 rating 전체 재계산:

```powershell
python manage.py rebuild_ratings
```

특정 카테고리만:

```powershell
python manage.py rebuild_ratings --board overall
```

실서비스에서는 `create_ranking_snapshot`을 하루 한 번 실행하면 등락을 안정적으로 보여줄 수 있습니다.

## 입시 데이터

CSV 필수 컬럼:

```text
university_name
admission_year
admission_phase
recruitment_unit
selection_category
selection_name
recruitment_group
recruitment_count
applicant_count
registered_count
competition_rate
```

추가 지표는 `metric_` 접두사로 넣습니다.

```text
metric_STUDENT_GRADE_70_CUT
metric_CSAT_PERCENTILE_70_CUT
metric_CONVERTED_SCORE_70_CUT
```

가져오기 예:

```powershell
python manage.py import_admissions_csv --file data/admissions_2026.csv --source-type ADIGA --source-url "출처 URL" --document-title "2026학년도 입시결과"
```

대학 단위 집계:

```powershell
python manage.py recalculate_admission_aggregates --year 2026
```

모집인원이 있는 경우 모집인원 가중평균을 사용합니다. 이 값은 공식 대학 평균이 아니라 K-unirank가 원자료를 기반으로 계산한 파생값입니다.

## API

```text
GET  /api/v1/boards/overall/next/
POST /api/v1/boards/overall/vote/
GET  /api/v1/boards/overall/ranking/?limit=50
```

POST JSON 예:

```json
{
  "university_a": 1,
  "university_b": 2,
  "selected_university": 1,
  "skipped": false
}
```

## Git에 올리지 않을 것

`.gitignore`에 아래가 포함되어 있습니다.

```text
.env
legacy/
.venv/
staticfiles/
```

`static/university/logos/`는 배포 시 고정 로고를 쓰기 위해 Git에 포함할 수 있습니다.

## Koyeb

배포 환경에서는 `DATABASE_URL`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`를 환경변수로 넣습니다. Dockerfile은 시작할 때 `migrate`, `collectstatic`, `gunicorn`을 실행합니다.

## 대학 주소와 캠퍼스 표기 정리

CareerNet 갱신 후 한 번 실행하면 기존 DB에 남아 있는 캠퍼스 중복과 지역 표기를 정리합니다.
한국폴리텍대학 캠퍼스는 합치지 않습니다.

먼저 미리보기:

```powershell
python manage.py normalize_university_data
```

반영:

```powershell
python manage.py normalize_university_data --apply
```

지역 표기는 `서울특별시`, `강원특별자치도`, `전북특별자치도`처럼 통일하고,
대학 목록 카드에는 전체 도로명 주소 대신 시·도만 일관되게 표시합니다.
대학 상세 화면에서는 정리된 전체 주소를 확인할 수 있습니다.

## ADIGA 입시결과 자동 가져오기

이 버전은 대입정보포털 어디가의 대학별 전형 결과 화면에서 공개된 모집단위 결과를 읽어
`AdmissionSource`, `AdmissionResult`, `AdmissionMetric`으로 저장합니다.
원문 URL과 수집 시점도 함께 보존합니다.

처음에는 특정 대학으로 파싱 결과만 확인하는 것을 권장합니다.

```powershell
python manage.py sync_adiga_admissions --university 단국대학교 --limit 2
```

정상적으로 모집단위 건수가 표시되면 실제 저장:

```powershell
python manage.py sync_adiga_admissions --university 단국대학교 --limit 2 --apply
```

전체 대학 저장:

```powershell
python manage.py sync_adiga_admissions --apply
```

한 번에 CareerNet 갱신 → 대학명/주소 정리 → ADIGA 입시결과 저장까지 실행하려면:

```powershell
python manage.py sync_kunirank_data
```

처음 시험할 때는 처리량을 제한할 수 있습니다.

```powershell
python manage.py sync_kunirank_data --adiga-limit 3
```

ADIGA 웹페이지 구조가 변경되면 파서도 수정이 필요할 수 있으므로,
전체 동기화 전에 소수 대학으로 먼저 확인하는 방식이 안전합니다.

현재 대표 입시 지표는 다음 기준으로 화면에 보여줍니다.

- 수시 학생부교과: 학생부등급 70% 컷이 공개된 경우 사용
- 정시 수능: 국어·수학·탐구 백분위 70% 컷이 공개된 경우 평균을 계산해 사용
- 대학마다 공개 방식이 다른 점수는 서로 섞어 하나의 공식 점수처럼 취급하지 않음
- 대학 단위 값은 모집인원이 있는 경우 모집인원 가중평균으로 계산한 K-unirank 파생값

## 대학 통합 기준

랭킹에서는 실제로 대학 자체가 통합된 경우만 하나로 합칩니다.
같은 법인의 이원화 캠퍼스나 분교는 각각 독립된 랭킹 항목으로 유지합니다.

예시:

- 단국대학교 죽전캠퍼스 / 단국대학교 천안캠퍼스: 분리
- 명지대학교 인문캠퍼스 / 명지대학교 자연캠퍼스: 분리
- 건국대학교 / 건국대학교 글로컬캠퍼스: 분리
- 고려대학교 / 고려대학교 세종캠퍼스: 분리
- 연세대학교 / 연세대학교 미래캠퍼스: 분리
- 한양대학교 / 한양대학교 ERICA캠퍼스: 분리
- 동국대학교 / 동국대학교 WISE캠퍼스: 분리
- 한국폴리텍대학 각 캠퍼스: 분리
- 강릉원주대학교 -> 강원대학교: 통합
- 안동대학교·경북도립대학교 -> 국립경국대학교: 통합

이전 버전에서 캠퍼스가 합쳐진 상태로 CareerNet 매핑이 저장되어 있어도
`sync_career_universities --apply --create-new`를 다시 실행하면 가능한 항목은 분리해서 다시 연결합니다.
