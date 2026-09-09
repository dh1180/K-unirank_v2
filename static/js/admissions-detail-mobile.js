(function () {
    'use strict';

    var mobileAdmissionMedia = window.matchMedia('(max-width: 720px)');

    function injectDesktopMetricRefinement() {
        if (document.getElementById('admissions-metric-refinement')) return;

        var style = document.createElement('style');
        style.id = 'admissions-metric-refinement';
        style.textContent = [
            '@media (min-width: 721px) {',
            '  .admissions-table-wrap .metric-stack-highlighted {',
            '    display: flex !important;',
            '    flex-direction: column !important;',
            '    align-items: flex-start !important;',
            '    gap: 6px !important;',
            '  }',
            '  .admissions-table-wrap .metric-item-featured {',
            '    width: auto !important;',
            '    max-width: 100% !important;',
            '    min-width: 0 !important;',
            '    min-height: 0 !important;',
            '    padding: 6px 10px !important;',
            '    display: inline-flex !important;',
            '    flex-direction: row !important;',
            '    align-items: baseline !important;',
            '    justify-content: flex-start !important;',
            '    gap: 6px !important;',
            '    border: 0 !important;',
            '    border-radius: 9px !important;',
            '    background: #f3f6fd !important;',
            '    box-shadow: none !important;',
            '  }',
            '  .admissions-table-wrap .metric-item-featured .metric-label,',
            '  .admissions-table-wrap .metric-stack-highlighted > .metric-item:not(.metric-item-featured) .metric-label {',
            '    color: #667085 !important;',
            '    font-size: 13px !important;',
            '    font-weight: 500 !important;',
            '    line-height: 1.55 !important;',
            '    letter-spacing: 0 !important;',
            '  }',
            '  .admissions-table-wrap .metric-item-featured .metric-value {',
            '    display: inline-flex !important;',
            '    align-items: baseline !important;',
            '    gap: 3px !important;',
            '    color: #3157e5 !important;',
            '    font-size: 13px !important;',
            '    font-weight: 700 !important;',
            '    line-height: 1.55 !important;',
            '    letter-spacing: 0 !important;',
            '  }',
            '  .admissions-table-wrap .metric-item-featured .metric-value small {',
            '    color: #667085 !important;',
            '    font-size: 13px !important;',
            '    font-weight: 600 !important;',
            '  }',
            '  .admissions-table-wrap .metric-stack-highlighted > .metric-item:not(.metric-item-featured) {',
            '    width: auto !important;',
            '    display: inline-flex !important;',
            '    align-items: baseline !important;',
            '    gap: 6px !important;',
            '    opacity: 1 !important;',
            '  }',
            '  .admissions-table-wrap .metric-stack-highlighted > .metric-item:not(.metric-item-featured) .metric-value {',
            '    color: #344054 !important;',
            '    font-size: 13px !important;',
            '    font-weight: 700 !important;',
            '    line-height: 1.55 !important;',
            '    letter-spacing: 0 !important;',
            '  }',
            '  .admissions-table-wrap .metric-stack-highlighted > .metric-item:not(.metric-item-featured) .metric-value small {',
            '    color: #667085 !important;',
            '    font-size: 13px !important;',
            '    font-weight: 600 !important;',
            '  }',
            '}',
        ].join('\n');
        document.head.appendChild(style);
    }

    function text(element) {
        return element ? String(element.textContent || '').replace(/\s+/g, ' ').trim() : '';
    }

    function make(tag, className, value) {
        var element = document.createElement(tag);
        if (className) element.className = className;
        if (value !== undefined && value !== null) element.textContent = value;
        return element;
    }

    function highlightDesktopMetrics(root) {
        var scope = root || document;
        var featuredLabels = {
            '학생부등급 50% 컷': 'grade',
            '학생부등급 70% 컷': 'grade',
            '공식 평균 백분위 50% 컷': 'percentile',
            '공식 평균 백분위 70% 컷': 'percentile'
        };

        scope.querySelectorAll('.admissions-table-wrap .metrics-cell .metric-stack').forEach(function (stack) {
            if (stack.classList.contains('metric-stack-highlighted')) return;

            var featured = [];
            Array.from(stack.querySelectorAll('.metric-item')).forEach(function (item) {
                var label = text(item.querySelector('.metric-label'));
                var kind = featuredLabels[label];
                if (!kind) return;

                item.classList.add('metric-item-featured');
                item.classList.add('metric-item-featured-' + kind);
                if (label.indexOf('50%') !== -1) item.classList.add('metric-item-featured-50');
                if (label.indexOf('70%') !== -1) item.classList.add('metric-item-featured-70');
                featured.push(item);
            });

            if (!featured.length) return;

            featured.sort(function (a, b) {
                var aLabel = text(a.querySelector('.metric-label'));
                var bLabel = text(b.querySelector('.metric-label'));
                var aOrder = aLabel.indexOf('50%') !== -1 ? 0 : 1;
                var bOrder = bLabel.indexOf('50%') !== -1 ? 0 : 1;
                return aOrder - bOrder;
            });
            featured.slice().reverse().forEach(function (item) {
                stack.insertBefore(item, stack.firstChild);
            });

            stack.classList.add('metric-stack-highlighted');
            stack.classList.add(featured.length === 1 ? 'metric-stack-featured-one' : 'metric-stack-featured-pair');
        });
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

    function boot() {
        injectDesktopMetricRefinement();
        highlightDesktopMetrics(document);
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
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
