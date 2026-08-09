K-unirank v60 - 입시 검색/필터 비동기 + 이전 테이블 UI 복원

변경
1. 하단 모집단위 결과
- 카드형 제거
- 이전 8열 테이블 디자인 복원
- 페이지당 60건

2. 비동기 검색
- 검색 버튼 제출 시 전체 페이지 reload 없음
- 입력 중 350ms debounce 자동 검색
- 대학명 / 학과명 / 전형명 검색

3. 비동기 필터
- 대학 유형: 전체 / 4년제 / 전문대
- 모집 구분: 전체 / 수시 / 정시
- 클릭 즉시 결과 영역만 갱신

4. 비동기 페이지네이션
- 처음 / 이전 / 다음 / 마지막도 fetch
- 결과 영역만 갱신
- 페이지 이동 시 탐색 섹션으로 부드럽게 스크롤

5. 주소창 동기화
- q/kind/phase/page가 querystring에 반영
- 새로고침 및 URL 공유 가능

6. 기존 v58/v59 내용 유지
- 농협대 수능평균 87.05 백분위 보정
- Procollege 0.00 결측치 처리
- 대표지표 2x2 TOP10
- admissions-overview.css 정상 로딩

추가 파일
- admissions/urls.py
- templates/admissions/partials/overview_results.html
- static/js/admissions-overview.js

DB migration 없음.

적용:
python manage.py check
python manage.py collectstatic --noinput --clear
python manage.py runserver

확인:
http://127.0.0.1:8000/admissions/

비동기 체크:
- 검색어 입력 -> 페이지 reload 없이 표 변경
- 전문대 클릭 -> URL kind=college 및 표만 변경
- 정시 클릭 -> phase=JEONGSI
- 다음 페이지 -> 전체 페이지 reload 없이 표 변경


v61 긴급 수정
- admissions/views.py _overview_result_context()
- 존재하지 않는 pagination_query 반환으로 NameError 발생하던 문제 수정

잘못된 코드:
"pagination_query": pagination_query

수정:
"pagination_query": pagination_params.urlencode()

DB 변경 없음
migration 없음

적용 후:
python manage.py check
python manage.py runserver

이번 수정은 Python 런타임 NameError 원인까지 검증했습니다.


v62 긴급 수정
- v60 템플릿 치환 과정에서 남은 예전 카드 HTML 조각 제거
- templates/admissions/overview.html 전체 블록 구조 재작성
- selected_year if/else를 하나의 정상 블록으로 정리
- overview.html 및 overview_results.html의 if/for/block/empty/else 짝 정적 검사 완료
- Python 파일 py_compile 검사 완료

DB 변경 없음 / migration 없음
적용 후:
python manage.py check
python manage.py runserver


v63 긴급 수정
- templates/admissions/partials/overview_results.html
- partial 내부에서 admission_metric_label 커스텀 필터를 사용하면서
  {% load admission_extras %}가 누락되어 TemplateSyntaxError가 발생하던 문제 수정

추가된 첫 줄:
{% load admission_extras %}

DB 변경 없음
migration 없음
재크롤링 없음

적용 후:
python manage.py check
python manage.py runserver


v64 핵심 수정
- _overview_result_context()가 AJAX querystring을 무시하던 버그 수정

기존 버그:
source_kind = ""
selected_phase = ""
query = ""

수정:
source_kind = request.GET.get("kind", "").strip().lower()
selected_phase = request.GET.get("phase", "").strip().upper()
query = request.GET.get("q", "").strip()

따라서 이제 실제로:
?q=항공&kind=four&phase=SUSI
를 보내면

- 대학명 / 모집단위 / 전형명에 '항공' 포함
- ADIGA(4년제)만
- SUSI(수시)만

서버에서 필터된 결과가 AJAX로 반환됩니다.

DB 변경 없음
migration 없음
재크롤링 없음

적용 후:
python manage.py check
python manage.py runserver

확인:
1. 검색창에 항공
2. 4년제 클릭
3. 수시 클릭
4. 페이지 전체 reload 없이 결과 표만 항공 + 4년제 + 수시로 바뀌어야 정상


v65
- 비동기 검색/필터 시 '불러오는 중...' 문구 제거
- spinner 제거
- 결과 표 높이 변동 없음
- 요청 중 기존 표만 opacity 0.72로 아주 살짝 흐려짐
- AJAX 완료 즉시 원상복구

DB/migration/재크롤링 없음.


v66 긴급 수정
- v65에서 남아 있던 admission-async-loading HTML DOM 자체 제거
- '불러오는 중...' 텍스트 완전 제거
- runtime html/js/css/py 전체에서
  '불러오는 중' / 'admission-async-loading' 문자열 0개 검증

비동기 요청 중:
- 문구 없음
- 스피너 없음
- 기존 결과 표만 살짝 흐려졌다가 새 결과로 교체

DB/migration/재크롤링 없음.


v67 - /admissions/ 모바일 최적화

데스크톱
- 기존 표 디자인 및 비동기 검색/필터 그대로 유지

모바일 (<=720px)
- overview hero 축소
- 통계 카드 가로 스와이프
- 대표지표 1열 TOP10 카드
- 검색창 + 검색 버튼 한 줄 유지
- 대학 유형 / 모집 구분 필터 가로 칩 스크롤
- 데스크톱 8열 table을 모바일에서 세로형 결과 카드로 CSS 변환
- 가로 table 스크롤 제거
- 페이지네이션 처음/마지막 숨김, 이전/다음 중심
- 390px 이하 초소형 화면 추가 보정

DB/migration/JS/크롤러 변경 없음.


v68 - 입시 결과 표 대표지표 글씨 크기 조정
- 데스크톱
  metric-label: 9px -> 11px
  metric-value: 10px -> 12px
  unit: 8px -> 9px
- 모바일
  metric-label: 10px
  metric-value: 11px

레이아웃/DB/JS 변경 없음.


v69 - 입결 순위 전용 페이지

신규 URL
/admissions/ranking/

구조
- 입결 찾기 / 입결 순위 상단 탭
- 학년도 선택
- 4년제 / 전문대 선택
- 수시 / 정시 선택
- 대학명 검색
- 대학 클릭 -> 해당 대학 입결 상세

4년제
수시:
- 학생부교과 70% 컷
- 등급 낮을수록 상위

정시:
- 공식 평균 백분위 70% 컷
- 백분위 높을수록 상위

전문대
수시:
- 학생부 합격자 평균 등급
- 낮을수록 상위

정시:
- 수능 합격자 평균 백분위
- 높을수록 상위

중요
- 4년제와 전문대는 절대 한 순위에 섞지 않음
- 동일 공개지표끼리만 비교
- 검색 시 원래 전체 순위 번호 유지
- 페이지당 50개
- 모바일 전용 순위 카드 레이아웃 포함

DB migration 없음.
현재 AdmissionAggregate / AdmissionMetric 데이터를 이용해 실시간 계산.


v70 - 상명대학교 서울/천안 캠퍼스 분리

공식 ADIGA 기준
- 서울: unvCd=0000117
- 천안: unvCd=0002959

서비스 표시
- 서울 -> 상명대학교
- 천안 -> 상명대학교 천안캠퍼스

핵심 정책
- 기존 "상명대학교" University PK는 서울이 그대로 사용
- 기존 투표/랭킹 관계는 서울에 그대로 보존
- 천안만 별도 University 생성
- UniversityCampus / UniversityExternalMapping을 서울/천안으로 분리
- ADIGA는 이름이 둘 다 "상명대학교"이므로 이름이 아니라 unvCd로 분리
- 기존 AdmissionSource / AdmissionResult도 source_url의 unvCd를 기준으로 이동
- 서울/천안 AdmissionAggregate만 재계산
- 향후 대학 동기화에서도 상명대를 하나로 다시 collapse하지 않도록 normalizer 변경

실행
1) 미리보기
python manage.py split_sangmyung_campuses

2) 실제 적용
python manage.py split_sangmyung_campuses --apply

3) 확인
python manage.py shell -c "from universities.models import University; print(list(University.objects.filter(name__startswith='상명대학교').values_list('university_id','name','region','address')))"

4) ADIGA mapping 확인
python manage.py shell -c "from universities.models import UniversityExternalMapping; print(list(UniversityExternalMapping.objects.filter(source='ADIGA',external_code__in=['0000117','0002959']).values_list('external_code','external_name','university__name')))"

DB schema migration 없음.


v71 - ADIGA 캠퍼스 통합 자동 감사

신규 명령:
python manage.py audit_adiga_campus_splits

목적:
- 현재 K-unirank에서는 하나의 University인데
- UniversityExternalMapping 기준 ADIGA external_code가 2개 이상 연결된 대학을 찾고
- 각 code의 캠퍼스명 / 주소 / 지역 / 해당 학년도 입결 건수를 비교
- 자동 분리 권고 여부를 출력

기본 출력:
- SPLIT_RECOMMENDED만 표시

보류 후보까지 모두:
python manage.py audit_adiga_campus_splits --all

특정 대학:
python manage.py audit_adiga_campus_splits --name 중앙대학교 --all

특정 학년도 입결 건수:
python manage.py audit_adiga_campus_splits --year 2026 --all

CSV 저장:
python manage.py audit_adiga_campus_splits --year 2026 --all --csv adiga-campus-audit.csv

판정:
SPLIT_RECOMMENDED
- 같은 University에 ADIGA code가 2개 이상
- 주소/지역이 서로 다르거나 캠퍼스 라벨이 명확히 다름

POLICY_REVIEW
- MERGED_UNIVERSITIES 또는 COLLAPSED_CAMPUS_BASES
- 현재 normalizer가 의도적으로 합치고 있는 대학
- 자동 분리 금지, 통합 이력/입시 구조 별도 검토

REVIEW
- code는 여러 개지만 현재 저장된 주소/캠퍼스 정보만으로 자동 판정하기 어려움

안전성:
- 읽기 전용
- DB 수정 없음
- migration 없음
- --apply 옵션 자체가 없음


v72 - ADIGA 캠퍼스 11개 대학 일괄 분리

분리 대상
1. 건양대학교
   0000054 논산/글로컬 -> 건양대학교
   0000055 대전/메디컬 -> 건양대학교 메디컬캠퍼스

2. 경기대학교
   0000056 수원 -> 경기대학교
   0000058 서울 -> 경기대학교 서울캠퍼스

3. 경동대학교
   0000060 고성/글로벌 -> 경동대학교
   0002574 원주/메디컬 -> 경동대학교 메디컬캠퍼스
   0002744 양주/메트로폴 -> 경동대학교 메트로폴캠퍼스

4. 신한대학교
   0002800 의정부 -> 신한대학교
   0002712 동두천 -> 신한대학교 동두천캠퍼스

5. 안양대학교
   0000147 안양 -> 안양대학교
   0000148 강화 -> 안양대학교 강화캠퍼스

6. 영산대학교
   0003193 해운대 -> 영산대학교
   0003194 양산 -> 영산대학교 양산캠퍼스

7. 을지대학교
   0000162 성남 -> 을지대학교
   0000161 대전 -> 을지대학교 대전캠퍼스
   0002911 의정부 -> 을지대학교 의정부캠퍼스

8. 전남대학교
   0000023 광주 -> 전남대학교
   0000024 여수 -> 전남대학교 여수캠퍼스

9. 중앙대학교
   0000175 서울 -> 중앙대학교
   0000174 안성/다빈치 -> 중앙대학교 다빈치캠퍼스

10. 예원예술대학교
    0000219 경기드림 -> 예원예술대학교
    0000218 전북희망 -> 예원예술대학교 전북희망캠퍼스

11. 인천가톨릭대학교
    0000167 송도국제 -> 인천가톨릭대학교
    0000168 강화 -> 인천가톨릭대학교 강화캠퍼스

통합 유지
- 강원대학교: MERGED_UNIVERSITIES 유지
- 가톨릭대학교: COLLAPSED_CAMPUS_BASES 유지
- 국립창원대학교: MERGED_UNIVERSITIES 추가
  경남도립거창/남해대학 옛 이름도 국립창원대학교 alias 추가

핵심 안전 정책
- 기존 대표 University PK 유지
- 기존 비교투표/Rating/랭킹 history는 대표 캠퍼스에 그대로 유지
- 새 캠퍼스에 과거 투표/Rating을 복제하지 않음
- AdmissionSource는 source_url의 exact unvCd로 이동
- AdmissionResult / RecruitmentUnit / Aggregate 함께 재배치
- 불명확 Campus는 억지로 이동하지 않고 로그에 보류
- 기본은 transaction 미리보기 / --apply만 실제 반영
- migration 없음

실행

1) Django 확인
python manage.py check

2) 전체 미리보기
python manage.py split_adiga_campuses_bulk

3) 특정 대학만 미리보기
python manage.py split_adiga_campuses_bulk --university 중앙대학교

4) 전체 적용
python manage.py split_adiga_campuses_bulk --apply

5) 캠퍼스 region 전체 미리보기
python manage.py repair_campus_regions

6) 캠퍼스 region 전체 적용
python manage.py repair_campus_regions --apply

7) 최종 감사
python manage.py audit_adiga_campus_splits --year 2026 --all

예상:
- 이번 11개 분리 대학은 동일 University 아래 multi-code 감사 목록에서 사라짐
- 강원대학교 / 국립창원대학교는 POLICY_REVIEW
- 가톨릭대학교는 POLICY_REVIEW


v73 - 전남 지역 표시명 통일

정책:
- 전남 -> 전남광주통합특별시
- 전라남도 -> 전남광주통합특별시
- 기존 전남광주통합특별시 값도 그대로 유지
- 광주광역시는 변경하지 않음

영향:
- University.location_label
- UniversityCampus.location_label
- 대학 찾기 카드의 지역 표시
- 대학 찾기 지역 필터 chip
- selected_region 필터 비교
- normalize_region()을 사용하는 향후 동기화/region 보정

DB schema migration 없음.
기존 address는 수정하지 않음.


v74 - 광주/전남 지역 표시명 최종 통일

서비스 표시 정책:
- 광주 -> 전남광주특별광역시
- 광주광역시 -> 전남광주특별광역시
- 전남 -> 전남광주특별광역시
- 전라남도 -> 전남광주특별광역시
- 전남광주통합특별시 -> 전남광주특별광역시
- 전남광주특별광역시 -> 그대로 유지

추가:
- normalize_address()에서 기존 "전남광주통합특별시 ..." 주소는
  "전남광주특별광역시 ..."로 표시 정규화

영향:
- 대학 찾기 카드
- 대학 찾기 지역 필터
- 대학 상세 상단 지역
- 캠퍼스 카드 지역
- University.location_label
- UniversityCampus.location_label

DB schema migration 없음.


v75 - 한국골프대학교 중복 병합

최종 University:
한국골프과학기술대학교

병합 대상:
한국골프대학교 -> 한국골프과학기술대학교

normalizer:
"한국골프대학교" -> "한국골프과학기술대학교"
향후 대학 동기화 시 구 교명으로 별도 University가 재생성되지 않도록 방지.

관리 명령:
python manage.py merge_korea_golf_university
python manage.py merge_korea_golf_university --apply

안전 정책:
- 기본 미리보기 / transaction rollback
- target University PK 유지
- target에 logo_path가 없고 source에 있으면 source 로고 보존
- Campus 이동
- UniversityExternalMapping 이동
- RecruitmentUnit 중복 정리
- AdmissionSource / AdmissionResult 이동
- AdmissionAggregate 재계산
- ComparisonVote의 University FK 이동
- UniversityRating 충돌 안전 처리
- RankingSnapshotItem 이동
- target/source 직접 VS 투표가 있으면 자동 병합 중단
- 양쪽 모두 실제 rating match_count가 있으면 자동 병합 중단
- 같은 snapshot에 두 대학이 동시에 존재하면 자동 병합 중단
- 처리하지 않은 다른 reverse FK 데이터가 남아 있으면 삭제 전 중단
- 마지막에만 "한국골프대학교" University 삭제

migration 없음.


v76 - 한국복지사이버대학 중복 병합

최종 University:
한국복지사이버대학교

병합 대상:
한국복지사이버대학 -> 한국복지사이버대학교

normalizer:
"한국복지사이버대학" -> "한국복지사이버대학교"
향후 대학 동기화 시 구/축약 교명으로 중복 University가 다시 만들어지지 않도록 방지.

관리 명령:
python manage.py merge_korea_welfare_cyber_university
python manage.py merge_korea_welfare_cyber_university --apply

병합 정책:
- 최종 이름은 한국복지사이버대학교
- target에 logo_path가 비어 있고 source에 로고가 있으면 source 로고 보존
- Campus / ExternalMapping 이동
- RecruitmentUnit 중복 정리
- AdmissionSource / AdmissionResult 이동
- AdmissionAggregate 재계산
- ComparisonVote / UniversityRating / RankingSnapshotItem 안전 이전
- 두 레코드 사이 직접 VS 투표가 있으면 중단
- 양쪽 모두 실제 rating 이력이 있으면 중단
- 같은 snapshot에 양쪽이 동시에 있으면 중단
- 미처리 reverse FK가 남아 있으면 삭제 전에 중단
- 최종적으로 한국복지사이버대학 중복 University 삭제

migration 없음.


v77 - 한국폴리텍 IV 대학 충남캠퍼스 로고 적용

대상:
한국폴리텍 IV 대학 충남캠퍼스

방식:
- 새 이미지 파일을 추가하지 않음
- DB에 이미 존재하는 같은 한국폴리텍 IV 대학의 logo_path를 재사용
- 우선순위:
  1. 대전캠퍼스
  2. 아산캠퍼스
  3. 청주캠퍼스
  4. 홍성캠퍼스
  5. 다른 IV 대학 캠퍼스
  6. 다른 한국폴리텍 대학의 기존 로고

실행:
python manage.py fix_polytech_chungnam_logo
python manage.py fix_polytech_chungnam_logo --apply

안전:
- 기본 미리보기
- --apply에서만 DB 반영
- University.logo_path만 수정
- 다른 대학/입결/투표/랭킹 데이터는 수정하지 않음
- migration 없음
