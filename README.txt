K-unirank v47 - Restore original V39 VS hover

1. templates/base.html 덮어쓰기
2. static/css/vs.css 덮어쓰기
3. python manage.py collectstatic --noinput --clear
4. git add .
5. git commit -m "style: 기존 VS 입시 hover 디자인 복원"
6. git push origin main

동작:
- 평소에는 로고/대학명/지역만 표시
- 마우스 hover/focus 시 카드 하단에 기존 V39 작은 입시 패널 표시
- 교과/수능 50%, 70% 유지
- 터치 환경에서는 hover 패널 숨김
