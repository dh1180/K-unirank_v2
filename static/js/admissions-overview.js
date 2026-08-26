(function () {
    'use strict';

    function compactAdmissionRows(root) {
        var scope = root || document;

        scope.querySelectorAll('.admissions-table-wrap tbody tr:not(.empty-table-row)').forEach(function (row) {
            if (row.querySelector('.mobile-admission-compact')) return;

            function cell(label) {
                return row.querySelector('td[data-label="' + label + '"]');
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

            var compact = document.createElement('td');
            compact.className = 'mobile-admission-compact';
            compact.colSpan = Math.max(row.children.length, 1);

            var universityCell = cell('대학');
            var phaseCell = cell('구분');
            var selectionCell = cell('전형');
            var unitCell = cell('모집단위');
            var recruitmentCell = cell('모집인원') || cell('모집');
            var competitionCell = cell('경쟁률');
            var metricsCell = cell('대표 지표') || cell('공개 지표');
            var sourceCell = cell('출처');
            var yearCell = cell('학년도');

            var top = make('div', 'mobile-result-top');
            var meta = make('div', 'mobile-result-meta');

            var universityLink = universityCell && universityCell.querySelector('.table-school-link');
            if (universityLink) {
                var compactUniversity = make('span', 'mobile-result-university', text(universityLink));
                meta.appendChild(compactUniversity);
            }

            if (yearCell) {
                if (meta.children.length) meta.appendChild(make('span', '', '·'));
                meta.appendChild(make('span', '', text(yearCell)));
            }

            var phaseText = text(phaseCell);
            if (phaseText) {
                var phase = make(
                    'span',
                    'mobile-result-phase' + (phaseText.indexOf('정시') !== -1 ? ' jeongsi' : ''),
                    phaseText
                );
                meta.appendChild(phase);
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

            row.insertBefore(compact, row.firstChild);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var explorer = document.getElementById('admission-explorer');
        if (!explorer) return;

        var resultsUrl = explorer.dataset.resultsUrl;
        var selectedYear = explorer.dataset.selectedYear;
        var resultsRegion = document.getElementById('admission-results-region');
        var countPill = document.getElementById('async-result-count');
        var form = document.getElementById('admission-async-search');
        var searchInput = document.getElementById('admission-search-input');
        var resetButton = document.getElementById('admission-filter-reset');
        var filterContainer = document.getElementById('admission-async-filters');
        var initialParams = new URLSearchParams(window.location.search);

        ensureTrackFilters(initialParams.get('track') || '');
        compactAdmissionRows(resultsRegion || document);

        var state = {
            q: searchInput ? searchInput.value.trim() : '',
            kind: activeFilterValue('kind'),
            phase: activeFilterValue('phase'),
            track: activeFilterValue('track'),
            page: '1'
        };

        var controller = null;
        var debounceTimer = null;

        function ensureTrackFilters(initialTrack) {
            if (!filterContainer || filterContainer.querySelector('[data-filter-group="track"]')) return;

            var group = document.createElement('div');
            group.className = 'filter-group admission-track-filter';
            group.dataset.filterGroup = 'track';

            var label = document.createElement('span');
            label.className = 'filter-label';
            label.textContent = '전형 유형';
            group.appendChild(label);

            [
                ['', '전체'],
                ['student', '학생부교과'],
                ['holistic', '학생부종합'],
                ['csat', '수능'],
                ['essay', '논술'],
                ['practical', '실기']
            ].forEach(function (item) {
                var button = document.createElement('button');
                button.type = 'button';
                button.className = 'explorer-chip js-async-filter';
                button.dataset.filter = 'track';
                button.dataset.value = item[0];
                button.textContent = item[1];
                button.classList.toggle('active', item[0] === initialTrack);
                group.appendChild(button);
            });

            filterContainer.insertBefore(group, resetButton || null);
        }

        function activeFilterValue(name) {
            var active = explorer.querySelector(
                '[data-filter="' + name + '"].active'
            );
            return active ? (active.dataset.value || '') : '';
        }

        function buildParams(page) {
            var params = new URLSearchParams();
            if (selectedYear) params.set('year', selectedYear);
            if (state.q) params.set('q', state.q);
            if (state.kind) params.set('kind', state.kind);
            if (state.phase) params.set('phase', state.phase);
            if (state.track) params.set('track', state.track);
            if (page && String(page) !== '1') params.set('page', String(page));
            return params;
        }

        function setActiveFilter(name, value) {
            explorer.querySelectorAll('[data-filter="' + name + '"]').forEach(
                function (button) {
                    button.classList.toggle(
                        'active',
                        (button.dataset.value || '') === value
                    );
                }
            );
        }

        function applyRecommendedPhase(track) {
            if (track === 'student' || track === 'holistic' || track === 'essay') {
                state.phase = 'SUSI';
                setActiveFilter('phase', 'SUSI');
            } else if (track === 'csat') {
                state.phase = 'JEONGSI';
                setActiveFilter('phase', 'JEONGSI');
            }
        }

        function setLoading(isLoading) {
            explorer.classList.toggle('is-loading', isLoading);
        }

        function updateCountFromPartial() {
            if (!countPill || !resultsRegion) return;
            var strong = resultsRegion.querySelector(
                '.async-results-meta strong'
            );
            if (strong) countPill.textContent = strong.textContent + '건';
        }

        function updateAddressBar(params) {
            var url = new URL(window.location.href);
            url.search = params.toString();
            window.history.replaceState(
                { admissionsAsync: true },
                '',
                url.pathname + (url.search ? '?' + url.searchParams.toString() : '')
            );
        }

        async function loadResults(options) {
            options = options || {};
            var page = options.page || '1';
            state.page = String(page);

            if (controller) controller.abort();
            controller = new AbortController();

            var params = buildParams(page);
            var requestUrl = resultsUrl + '?' + params.toString();

            setLoading(true);

            try {
                var response = await fetch(requestUrl, {
                    method: 'GET',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    signal: controller.signal,
                    credentials: 'same-origin'
                });

                if (!response.ok) {
                    throw new Error('입시 결과를 불러오지 못했습니다.');
                }

                var html = await response.text();
                resultsRegion.innerHTML = html;
                compactAdmissionRows(resultsRegion);

                updateCountFromPartial();
                updateAddressBar(params);

                if (options.scroll) {
                    explorer.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }

                if (typeof window.kuniTrack === 'function') {
                    window.kuniTrack('admission_async_filter', {
                        search_term: state.q || undefined,
                        university_kind: state.kind || 'all',
                        phase: state.phase || 'all',
                        admission_track: state.track || 'all',
                        page: Number(page || 1)
                    });
                }
            } catch (error) {
                if (error.name === 'AbortError') return;

                resultsRegion.innerHTML =
                    '<div class="async-error">' +
                    '<strong>결과를 불러오지 못했어요.</strong>' +
                    '<span>잠시 후 다시 시도해주세요.</span>' +
                    '</div>';
            } finally {
                setLoading(false);
            }
        }

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            state.q = searchInput.value.trim();
            loadResults({ page: '1' });
        });

        searchInput.addEventListener('input', function () {
            window.clearTimeout(debounceTimer);
            debounceTimer = window.setTimeout(function () {
                state.q = searchInput.value.trim();
                loadResults({ page: '1' });
            }, 350);
        });

        explorer.addEventListener('click', function (event) {
            var filter = event.target.closest('.js-async-filter');
            if (filter) {
                event.preventDefault();

                var name = filter.dataset.filter;
                var value = filter.dataset.value || '';

                state[name] = value;
                setActiveFilter(name, value);

                if (name === 'track') {
                    applyRecommendedPhase(value);
                }

                loadResults({ page: '1' });
                return;
            }

            var pageLink = event.target.closest('.js-async-page');
            if (pageLink) {
                event.preventDefault();

                var href = new URL(
                    pageLink.getAttribute('href'),
                    window.location.origin
                );
                var page = href.searchParams.get('page') || '1';
                loadResults({ page: page, scroll: true });
            }
        });

        resetButton.addEventListener('click', function () {
            state.q = '';
            state.kind = '';
            state.phase = '';
            state.track = '';
            state.page = '1';

            searchInput.value = '';
            setActiveFilter('kind', '');
            setActiveFilter('phase', '');
            setActiveFilter('track', '');

            loadResults({ page: '1' });
        });

        window.addEventListener('popstate', function () {
            var params = new URLSearchParams(window.location.search);

            state.q = params.get('q') || '';
            state.kind = params.get('kind') || '';
            state.phase = params.get('phase') || '';
            state.track = params.get('track') || '';
            state.page = params.get('page') || '1';

            searchInput.value = state.q;
            setActiveFilter('kind', state.kind);
            setActiveFilter('phase', state.phase);
            setActiveFilter('track', state.track);

            loadResults({ page: state.page });
        });
    });
})();
