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
    var mobileAdmissionMedia = window.matchMedia('(max-width: 720px)');

    function text(element) {
        return element ? String(element.textContent || '').replace(/\s+/g, ' ').trim() : '';
    }

    function make(tag, className, value) {
        var element = document.createElement(tag);
        if (className) element.className = className;
        if (value !== undefined && value !== null) element.textContent = value;
        return element;
    }

    function compactAdmissionRows(root) {
        var scope = root || document;

        if (!mobileAdmissionMedia.matches) {
            scope.querySelectorAll('.mobile-admission-compact').forEach(function (compact) {
                compact.remove();
            });
            return;
        }

        scope.querySelectorAll('.admissions-table-wrap tbody tr:not(.empty-table-row)').forEach(function (row) {
            if (row.querySelector('.mobile-admission-compact')) return;

            function cell(label) {
                return row.querySelector('td[data-label="' + label + '"]');
            }

            var compact = document.createElement('td');
            compact.className = 'mobile-admission-compact';
            compact.colSpan = Math.max(row.children.length, 1);

            var yearCell = cell('학년도');
            var phaseCell = cell('구분');
            var selectionCell = cell('전형');
            var unitCell = cell('모집단위');
            var recruitmentCell = cell('모집');
            var competitionCell = cell('경쟁률');
            var metricsCell = cell('공개 지표');
            var sourceCell = cell('출처');

            var top = make('div', 'mobile-result-top');
            var meta = make('div', 'mobile-result-meta');
            if (yearCell) meta.appendChild(make('span', '', text(yearCell)));

            var phaseText = text(phaseCell);
            if (phaseText) {
                meta.appendChild(make(
                    'span',
                    'mobile-result-phase' + (phaseText.indexOf('정시') !== -1 ? ' jeongsi' : ''),
                    phaseText
                ));
            }
            top.appendChild(meta);

            var favorite = unitCell && unitCell.querySelector('.favorite-inline-form, .favorite-button.compact');
            if (favorite) top.appendChild(favorite.cloneNode(true));
            compact.appendChild(top);

            var main = make('div', 'mobile-result-main');
            var unitName = unitCell && unitCell.querySelector('.unit-name');
            main.appendChild(make('strong', 'mobile-result-unit', text(unitName) || text(unitCell) || '-'));

            var selectionParts = selectionCell
                ? Array.from(selectionCell.querySelectorAll('strong, small')).map(text).filter(Boolean)
                : [];
            if (!selectionParts.length && selectionCell) selectionParts = [text(selectionCell)];

            var campus = unitCell && unitCell.querySelector('small.subtle');
            var selectionLine = selectionParts.join(' · ');
            if (campus && text(campus)) {
                selectionLine += (selectionLine ? ' · ' : '') + text(campus);
            }
            if (selectionLine) main.appendChild(make('div', 'mobile-result-selection', selectionLine));
            compact.appendChild(main);

            var metricItems = metricsCell
                ? Array.from(metricsCell.querySelectorAll('.metric-item')).map(function (item) {
                    return {
                        label: text(item.querySelector('.metric-label')),
                        value: text(item.querySelector('.metric-value'))
                    };
                }).filter(function (item) { return item.label && item.value; })
                : [];

            var pairPriorities = phaseText.indexOf('정시') !== -1
                ? [
                    ['공식 평균 백분위 50% 컷', '공식 평균 백분위 70% 컷'],
                    ['수능 환산점수 50% 컷', '수능 환산점수 70% 컷'],
                    ['평균 수능등급 50% 컷', '평균 수능등급 70% 컷']
                ]
                : [
                    ['학생부등급 50% 컷', '학생부등급 70% 컷'],
                    ['대학 환산점수 50% 컷', '대학 환산점수 70% 컷']
                ];

            var selectedMetrics = [];
            pairPriorities.some(function (labels) {
                var pair = labels.map(function (label) {
                    return metricItems.find(function (item) { return item.label === label; });
                }).filter(Boolean);
                if (pair.length) {
                    selectedMetrics = pair;
                    return true;
                }
                return false;
            });

            if (!selectedMetrics.length) {
                selectedMetrics = metricItems.filter(function (item) {
                    return item.label.indexOf('50% 컷') !== -1 || item.label.indexOf('70% 컷') !== -1;
                }).slice(0, 2);
            }

            var cutline = make('div', 'mobile-result-cutline');
            if (selectedMetrics.length) {
                selectedMetrics.forEach(function (metric) {
                    var cut = make('span', 'mobile-cut-item');
                    var cutLabel = metric.label.indexOf('50% 컷') !== -1 ? '50%' :
                        (metric.label.indexOf('70% 컷') !== -1 ? '70%' : '컷');
                    cut.appendChild(make('b', '', cutLabel));

                    var valueParts = metric.value.match(/^([\d.,-]+)\s*(.*)$/);
                    if (valueParts) {
                        cut.appendChild(make('strong', '', valueParts[1]));
                        if (valueParts[2]) cut.appendChild(make('small', '', valueParts[2]));
                    } else {
                        cut.appendChild(make('strong', '', metric.value));
                    }
                    cutline.appendChild(cut);
                });
            } else {
                cutline.appendChild(make('span', 'mobile-cut-empty', '50·70% 컷 미공개'));
            }
            compact.appendChild(cutline);

            var bottom = make('div', 'mobile-result-bottom');
            var recruitment = text(recruitmentCell);
            var competition = text(competitionCell);
            if (recruitment && recruitment !== '-') bottom.appendChild(make('span', '', '모집 ' + recruitment));
            if (competition && competition !== '-') bottom.appendChild(make('span', '', '경쟁률 ' + competition));

            var sourceLink = sourceCell && sourceCell.querySelector('a[href]');
            if (sourceLink) {
                var compactSource = make('a', 'mobile-source-link', '원문 ↗');
                compactSource.href = sourceLink.href;
                compactSource.target = sourceLink.target || '_blank';
                compactSource.rel = sourceLink.rel || 'noopener';
                bottom.appendChild(compactSource);
            }
            compact.appendChild(bottom);

            row.appendChild(compact);
        });
    }

    var card = document.querySelector('.admission-control-card');
    if (card) {
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
    }

    compactAdmissionRows(document);
    if (typeof mobileAdmissionMedia.addEventListener === 'function') {
        mobileAdmissionMedia.addEventListener('change', function () {
            compactAdmissionRows(document);
        });
    } else if (typeof mobileAdmissionMedia.addListener === 'function') {
        mobileAdmissionMedia.addListener(function () {
            compactAdmissionRows(document);
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
