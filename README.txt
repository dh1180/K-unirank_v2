K-unirank v52 - 지역 미상 대학 대표주소 제1캠퍼스 보정

목적
- University 상단이 '지역 미상'인 대학만 대상
- CareerNet UniversityCampus 중
  1) is_primary=True
  2) 본교 / 본캠퍼스 / 제1캠퍼스 / 1캠퍼스
  순서로 대표 캠퍼스를 선택
- 해당 캠퍼스의 주소 + 지역을 University.address / University.region에 저장
- 제2캠퍼스를 임의로 대표로 선택하지 않음

예시
가천대학교
기존:
  지역 미상
  인천 연수구 함박뫼로 191

보정:
  경기도
  경기도 성남시 수정구 성남대로 1342 (복정동, 가천대학교)

적용 파일
universities/management/commands/backfill_primary_campus_address.py

1. 코드 확인
python manage.py check

2. 가천대만 미리보기
python manage.py backfill_primary_campus_address --university "가천대학교"

3. 전체 지역 미상 대학 미리보기
python manage.py backfill_primary_campus_address

4. 실제 반영
python manage.py backfill_primary_campus_address --apply

5. 확인
python manage.py shell -c "from universities.models import University; u=University.objects.get(name='가천대학교'); print(u.name, u.location_label, u.display_address)"

실서버
railway ssh -s web -- python manage.py backfill_primary_campus_address
railway ssh -s web -- python manage.py backfill_primary_campus_address --apply

주의
- University / Campus / Admission / Ranking 데이터 삭제 없음
- 지역 미상이 아닌 대학은 건드리지 않음
- 제1캠퍼스를 확인할 수 없는 대학은 경고만 출력하고 건너뜀
