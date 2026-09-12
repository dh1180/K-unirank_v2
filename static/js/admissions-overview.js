(function () {
    'use strict';

    var mobileAdmissionMedia = window.matchMedia('(max-width: 720px)');

    function compactAdmissionRows(root) {
        var scope = root || document;

        if (!mobileAdmissionMedia.matches) {
            scope.querySelectorAll('.mobile-admission-compact').forEach(function (compact) {
                compact.parentElement.classList.remove('has-mobile-compact');
                compact.remove();
            });
            return;
        }

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
                var compactUniversity = make('a', 'mobile-result-university', text(universityLink));
                compactUniversity.href = universityLink.href;
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
            var unitHref = unitName && unitName.getAttribute('href');
            var compactUnit = make(unitHref ? 'a' : 'strong', 'mobile-result-unit', text(unitName) || text(unitCell) || '-');
            if (unitHref) compactUnit.href = unitHref;
            main.appendChild(compactUnit);

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

            if (!selectedMetrics.length) {
                selectedMetrics = metricItems.filter(function (item) {
                    return item.label.indexOf('합격자 평균') !== -1 || item.label.indexOf('합격자 최저') !== -1;
                }).slice(0, 2);
            }

            var cutline = make('div', 'mobile-result-cutline');
            if (selectedMetrics.length) {
                selectedMetrics.forEach(function (metric) {
                    var cut = make('span', 'mobile-cut-item');
                    var cutLabel = metric.label.indexOf('50% 컷') !== -1 ? '50%' :
                        (metric.label.indexOf('70% 컷') !== -1 ? '70%' :
                            (metric.label.indexOf('평균') !== -1 ? '평균' : '최저'));
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
                cutline.appendChild(make('span', 'mobile-cut-empty', '대표 성적 지표 미공개'));
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
            row.classList.add('has-mobile-compact');
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var explorer = document.getElementById('admission-explorer');
        if (!explorer) return;
        var resultsRegion = document.getElementById('admission-results-region');
        var form = document.getElementById('admission-async-search');
        var searchInput = document.getElementById('admission-search-input');
        var yearSelect = document.getElementById('admission-year');
        var countPill = document.getElementById('async-result-count');
        var status = document.getElementById('admission-search-status');
        var errorBanner = document.getElementById('admission-search-error');
        var resetLink = document.getElementById('admission-filter-reset');
        var heroForm = document.querySelector('.home-hero-search');
        if (!resultsRegion || !form || !searchInput) return;

        var state = readRenderedState();
        var controller = null;
        var revision = 0;
        var debounceTimer = null;
        var composing = false;

        function readRenderedState() {
            var meta = resultsRegion.querySelector('.async-results-meta');
            return {
                year: meta.dataset.year || explorer.dataset.selectedYear,
                q: meta.dataset.query || '',
                kind: meta.dataset.kind || '',
                phase: meta.dataset.phase || '',
                track: meta.dataset.track || '',
                page: meta.dataset.page || '1'
            };
        }

        function fromParams(params) {
            return {
                year: params.get('year') || explorer.dataset.selectedYear,
                q: params.get('q') || '', kind: params.get('kind') || '',
                phase: params.get('phase') || '', track: params.get('track') || '',
                page: params.get('page') || '1'
            };
        }

        function paramsFor(values) {
            var params = new URLSearchParams();
            ['year', 'q', 'kind', 'phase', 'track', 'page'].forEach(function (name) {
                if (values[name] && !(name === 'page' && values[name] === '1')) {
                    params.set(name, values[name]);
                }
            });
            return params;
        }

        function suggestedPhase(track) {
            if (['student', 'holistic', 'essay'].includes(track)) return 'SUSI';
            return track === 'csat' ? 'JEONGSI' : '';
        }

        function withFilter(name, value) {
            var next = Object.assign({}, state, { page: '1' });
            next[name] = value;
            if (name === 'track' && suggestedPhase(value)) next.phase = suggestedPhase(value);
            if (name === 'phase' && suggestedPhase(next.track) && suggestedPhase(next.track) !== value) {
                next.track = '';
            }
            return next;
        }

        function syncControls() {
            searchInput.value = state.q;
            if (heroForm) heroForm.elements.q.value = state.q;
            explorer.querySelectorAll('.js-async-filter').forEach(function (link) {
                var active = state[link.dataset.filter] === link.dataset.value;
                link.classList.toggle('active', active);
                if (active) link.setAttribute('aria-current', 'true');
                else link.removeAttribute('aria-current');
                link.href = '?' + paramsFor(withFilter(link.dataset.filter, link.dataset.value)) + '#admission-explorer';
            });
            ['kind', 'phase', 'track'].forEach(function (name) { form.elements[name].value = state[name]; });
            resetLink.href = '?year=' + encodeURIComponent(state.year) + '#admission-explorer';
        }

        function setLoading(loading) {
            explorer.classList.toggle('is-loading', loading);
            resultsRegion.setAttribute('aria-busy', String(loading));
        }

        // Invalidate as soon as intent changes, including the debounce/IME interval.
        // A cancelled fetch may already have completed response.text().
        function invalidate() {
            window.clearTimeout(debounceTimer);
            if (controller) controller.abort();
            revision += 1;
            setLoading(false);
        }

        function scrollToResults() {
            explorer.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
        }

        async function loadResults(options) {
            options = options || {};
            invalidate();
            var requestRevision = revision;
            var requestState = Object.assign({}, state);
            var requestController = new AbortController();
            controller = requestController;
            syncControls();
            errorBanner.hidden = true;
            status.textContent = '조건에 맞는 입결을 찾고 있어요…';
            setLoading(true);
            try {
                var response = await fetch(explorer.dataset.resultsUrl + '?' + paramsFor(requestState), {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    signal: requestController.signal,
                    credentials: 'same-origin'
                });
                if (!response.ok) throw new Error('Search failed');
                var html = await response.text();
                if (requestRevision !== revision) return;
                var fragment = document.createElement('template');
                fragment.innerHTML = html;
                if (!fragment.content.querySelector('.async-results-meta[data-page]')) throw new Error('Invalid results');
                resultsRegion.replaceChildren(fragment.content);
                state = readRenderedState();
                syncControls();
                compactAdmissionRows(resultsRegion);
                var meta = resultsRegion.querySelector('.async-results-meta');
                countPill.textContent = Number(meta.dataset.count).toLocaleString('ko-KR') + '건';
                status.textContent = countPill.textContent + '의 검색 결과를 표시했어요.';
                var url = window.location.pathname + '?' + paramsFor(state) + '#admission-explorer';
                if (options.history !== false && url !== window.location.pathname + window.location.search + window.location.hash) {
                    window.history.pushState({ admissionsAsync: true }, '', url);
                }
                if (options.scroll) scrollToResults();
                if (typeof window.kuniTrack === 'function' && options.history !== false) {
                    window.kuniTrack('admission_async_filter', { search_term: state.q || undefined,
                        university_kind: state.kind || 'all', phase: state.phase || 'all',
                        admission_track: state.track || 'all', page: Number(state.page) });
                }
            } catch (error) {
                if (requestRevision !== revision || error.name === 'AbortError') return;
                // Preserve the last successful results and give the current query a retry.
                errorBanner.hidden = false;
                status.textContent = '검색에 실패했어요. 이전 결과를 유지했어요. 다시 시도할 수 있어요.';
            } finally {
                if (requestRevision === revision) setLoading(false);
            }
        }

        function scheduleSearch() {
            invalidate();
            status.textContent = '';
            if (composing) return;
            debounceTimer = window.setTimeout(function () {
                state.q = searchInput.value.trim();
                state.page = '1';
                loadResults();
            }, 350);
        }

        form.addEventListener('submit', function (event) {
            if (composing) { event.preventDefault(); return; }
            // A new year needs the full response: coverage and highlights also change.
            if (yearSelect && yearSelect.value !== state.year) return;
            event.preventDefault();
            state.q = searchInput.value.trim();
            state.page = '1';
            loadResults();
        });
        if (yearSelect) yearSelect.addEventListener('change', function () {
            invalidate();
            form.requestSubmit();
        });
        searchInput.addEventListener('compositionstart', function () { composing = true; invalidate(); });
        searchInput.addEventListener('compositionend', function () { composing = false; scheduleSearch(); });
        searchInput.addEventListener('input', scheduleSearch);

        if (heroForm) heroForm.addEventListener('submit', function (event) {
            event.preventDefault();
            state = { year: state.year, q: heroForm.elements.q.value.trim(), kind: '', phase: '', track: '', page: '1' };
            loadResults({ scroll: true });
        });

        document.querySelector('.home-discovery').addEventListener('click', function (event) {
            // Retain native new-tab / modified-click behavior for every real link.
            if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            var example = event.target.closest('[data-search-term]');
            if (example) {
                event.preventDefault();
                state.q = example.dataset.searchTerm;
                state.page = '1';
                loadResults({ scroll: true });
                return;
            }
            var filter = event.target.closest('.js-async-filter');
            if (filter) {
                event.preventDefault();
                state.q = searchInput.value.trim();
                state = withFilter(filter.dataset.filter, filter.dataset.value);
                loadResults();
                return;
            }
            var pageLink = event.target.closest('.js-async-page');
            if (pageLink) {
                event.preventDefault();
                // The displayed pager belongs to the last successful result set.
                state = fromParams(new URL(pageLink.href).searchParams);
                loadResults({ scroll: true });
                return;
            }
            if (event.target.closest('#admission-filter-reset, [data-reset-search]')) {
                event.preventDefault();
                state = { year: state.year, q: '', kind: '', phase: '', track: '', page: '1' };
                loadResults();
            }
        });
        document.getElementById('admission-search-retry').addEventListener('click', function () { loadResults(); });
        window.addEventListener('popstate', function () {
            state = fromParams(new URLSearchParams(window.location.search));
            if (state.year !== explorer.dataset.selectedYear) { window.location.reload(); return; }
            loadResults({ history: false });
        });
        syncControls();
        compactAdmissionRows(resultsRegion);
        if (typeof mobileAdmissionMedia.addEventListener === 'function') {
            mobileAdmissionMedia.addEventListener('change', function () { compactAdmissionRows(resultsRegion); });
        } else if (typeof mobileAdmissionMedia.addListener === 'function') {
            mobileAdmissionMedia.addListener(function () { compactAdmissionRows(resultsRegion); });
        }
    });
})();
