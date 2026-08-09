K-unirank v51 CLEAN RANKING START

목표
- 운영자 초기 시드 완전 제거
- synthetic n전 제거
- 기존 테스트/실제 투표 포함 랭킹 데이터 초기화
- 모든 대학은 동일한 1500 / RD 350 / 0전에서 시작
- 이후 실제 ComparisonVote만 점수/전적에 반영

절대 삭제하지 않는 데이터
- University / UniversityCampus
- CareerNet / ADIGA 외부 매핑
- 입시 AdmissionResult / AdmissionMetric / AdmissionAggregate
- 대학 로고 및 static
- 사용자 계정

코드 적용 파일
- rankings/baseline.py
- rankings/views.py
- rankings/management/commands/seed_ranking_baseline.py
- rankings/management/commands/reset_ranking_clean.py
- templates/rankings/home.html
- templates/rankings/ranking.html
- universities/views.py
- templates/universities/university_detail.html

1. 파일 덮어쓰기 후
python manage.py check

2. 삭제 예정 데이터 확인 (DB 변경 없음)
python manage.py reset_ranking_clean

3. 출력 확인 후 실제 랭킹 데이터만 초기화
python manage.py reset_ranking_clean --apply

4. 확인
python manage.py shell -c "from rankings.models import ComparisonVote, UniversityRating; print('votes=', ComparisonVote.objects.count(), 'ratings=', UniversityRating.objects.count())"

정상:
votes= 0 ratings= 0

이후 사이트 상태
- 메인 종합 유효 투표: 0
- TOP10: 비어 있음
- 전체 랭킹: 비어 있음
- 대학 상세: '아직 실제 비교 기록이 없어요.'
- 첫 실제 VS 투표 시 해당 두 대학이 1500점 중립 상태에서 Glicko-2 계산 시작

주의
reset_ranking_clean --apply는 현재 존재하는 실제 투표도 모두 삭제한다.
한번 삭제하면 DB 백업 없이는 복구할 수 없다.
