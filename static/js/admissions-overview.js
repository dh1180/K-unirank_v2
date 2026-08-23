(function () {
    'use strict';

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
