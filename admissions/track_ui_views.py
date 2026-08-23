import json
import re
from html import escape

from django.urls import reverse

from universities.models import University

from .models import AdmissionResult
from .university_detail_views import university_admissions as filtered_university_admissions


TRACK_SCRIPT = r'''
<script>
(function () {
    var card = document.querySelector('.admission-control-card');
    if (!card) return;

    var params = new URLSearchParams(window.location.search);
    var current = params.get('track') || '';
    var options = [
        ['', '전체'],
        ['student', '학생부교과'],
        ['holistic', '학생부종합'],
        ['csat', '수능'],
        ['essay', '논술'],
        ['practical', '실기']
    ];

    var wrap = document.createElement('div');
    wrap.className = 'region-chips admission-track-tabs';
    wrap.setAttribute('aria-label', '전형 유형');
    wrap.style.marginTop = '10px';

    options.forEach(function (item) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'region-chip' + (current === item[0] ? ' active' : '');
        button.textContent = item[1];
        button.addEventListener('click', function () {
            var next = new URLSearchParams(window.location.search);
            next.delete('page');
            if (item[0]) next.set('track', item[0]);
            else next.delete('track');

            if (item[0] === 'student' || item[0] === 'holistic' || item[0] === 'essay') {
                next.set('phase', 'SUSI');
            } else if (item[0] === 'csat') {
                next.set('phase', 'JEONGSI');
            }
            window.location.href = window.location.pathname + '?' + next.toString() + '#admission-unit-results';
        });
        wrap.appendChild(button);
    });

    var filterRow = card.querySelector('.admission-filter-row');
    if (filterRow) filterRow.insertAdjacentElement('afterend', wrap);

    if (current) {
        document.querySelectorAll('.admission-search-form, .detail-results-search').forEach(function (form) {
            if (form.querySelector('input[name="track"]')) return;
            var input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'track';
            input.value = current;
            form.appendChild(input);
        });

        document.querySelectorAll('.admission-control-card a[href^="?"], #admission-unit-results .results-pager a[href^="?"]').forEach(function (link) {
            var url = new URL(link.getAttribute('href'), window.location.origin + window.location.pathname);
            url.searchParams.set('track', current);
            link.setAttribute('href', url.pathname + '?' + url.searchParams.toString() + url.hash);
        });
    }
})();
</script>
'''


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
    admissions_url = f"https://www.k-unirank.com{canonical_path}"
    university_url = f"https://www.k-unirank.com{university_path}"

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
                    "url": "https://www.k-unirank.com/",
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "K-unirank",
                        "item": "https://www.k-unirank.com/",
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "대학 찾기",
                        "item": "https://www.k-unirank.com/universities/",
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

    if "</body>" in html:
        html = html.replace("</body>", TRACK_SCRIPT + "\n</body>", 1)

    response.content = html.encode(response.charset or "utf-8")
    return response
