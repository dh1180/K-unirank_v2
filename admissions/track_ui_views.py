import json
import re
from html import escape

from django.templatetags.static import static
from django.urls import reverse

from universities.models import University

from .models import AdmissionResult
from .university_detail_views import university_admissions as filtered_university_admissions


def _replace_meta(html, attribute, value):
    escaped_value = escape(value, quote=True)
    pattern = rf'(<meta\s+{re.escape(attribute)}\s+content=")[^"]*(">)'
    return re.sub(pattern, rf'\g<1>{escaped_value}\g<2>', html, count=1, flags=re.IGNORECASE)


def _inject_admission_seo(html, university, latest_year):
    year_label = f"{latest_year} " if latest_year else ""
    title = f"{university.name} 입결 | {year_label}수시·정시·학과별 입시결과 | K-unirank"
    description = (
        f"{university.name} 입결을 확인하세요. "
        f"{latest_year or '최신'}학년도 수시 학생부교과·학생부종합, 정시 수능, 논술·실기와 "
        "학과·모집단위별 50%·70% 컷, 경쟁률, 공식 원문 출처를 제공합니다."
    )
    short_description = (
        f"{university.name}의 {latest_year or '최신'}학년도 수시·정시 입결과 "
        "학과별 모집단위 결과를 확인하세요."
    )

    html = re.sub(
        r"<title>.*?</title>",
        f"<title>{escape(title)}</title>",
        html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html = _replace_meta(html, 'name="description"', description)
    html = _replace_meta(html, 'property="og:title"', title)
    html = _replace_meta(html, 'property="og:description"', short_description)
    html = _replace_meta(html, 'name="twitter:title"', title)
    html = _replace_meta(html, 'name="twitter:description"', short_description)

    canonical_path = reverse("admissions:university", args=[university.pk])
    university_path = reverse("universities:detail", args=[university.pk])
    admissions_url = f"https://k-unirank.com{canonical_path}"
    university_url = f"https://k-unirank.com{university_path}"

    structured_data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": f"{admissions_url}#webpage",
                "url": admissions_url,
                "name": title,
                "description": description,
                "inLanguage": "ko-KR",
                "about": {
                    "@type": "CollegeOrUniversity",
                    "name": university.name,
                    "url": university_url,
                    "address": university.display_address,
                },
                "isPartOf": {
                    "@type": "WebSite",
                    "name": "K-unirank",
                    "url": "https://k-unirank.com/",
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "K-unirank",
                        "item": "https://k-unirank.com/",
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "대학 찾기",
                        "item": "https://k-unirank.com/universities/",
                    },
                    {
                        "@type": "ListItem",
                        "position": 3,
                        "name": university.name,
                        "item": university_url,
                    },
                    {
                        "@type": "ListItem",
                        "position": 4,
                        "name": f"{university.name} 입시 결과",
                        "item": admissions_url,
                    },
                ],
            },
        ],
    }
    json_ld = json.dumps(structured_data, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace(
        "</head>",
        f'<script type="application/ld+json">{json_ld}</script>\n</head>',
        1,
    )
    return html


def _inject_detail_mobile_script(html):
    if "</body>" not in html:
        return html

    script_url = escape(static("js/admissions-detail-mobile.js"), quote=True)
    script_tag = f'<script defer src="{script_url}"></script>'
    return html.replace("</body>", script_tag + "\n</body>", 1)


def university_admissions(request, university_id):
    response = filtered_university_admissions(request, university_id)
    if response.status_code != 200 or not hasattr(response, "content"):
        return response

    university = University.objects.filter(pk=university_id, is_active=True).first()
    latest_year = None
    if university is not None:
        latest_year = (
            AdmissionResult.objects.filter(university=university)
            .order_by("-admission_year")
            .values_list("admission_year", flat=True)
            .first()
        )

    html = response.content.decode(response.charset or "utf-8")
    if university is not None:
        html = _inject_admission_seo(html, university, latest_year)

    # 전형 유형 필터는 templates/admissions/university.html에서 한 번만 렌더링한다.
    # 여기서는 모바일 결과 압축 스크립트만 추가한다.
    html = _inject_detail_mobile_script(html)

    response.content = html.encode(response.charset or "utf-8")
    return response
