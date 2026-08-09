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
