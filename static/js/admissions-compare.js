(function () {
    var activeRequest = null;
    var requestSerial = 0;

    function resultsSection() {
        return document.querySelector('[data-compare-results]');
    }

    function scrollToResults(behavior) {
        var section = resultsSection();
        if (!section) return;
        section.scrollIntoView({ behavior: behavior || 'auto', block: 'start' });
    }

    function loadResults(url, options) {
        var currentSection = resultsSection();
        if (!currentSection || typeof window.fetch !== 'function' || typeof window.DOMParser !== 'function') {
            window.location.assign(url);
            return;
        }

        if (activeRequest) activeRequest.abort();
        var requestId = ++requestSerial;
        var controller = typeof window.AbortController === 'function' ? new AbortController() : null;
        activeRequest = controller;
        currentSection.setAttribute('aria-busy', 'true');
        currentSection.classList.add('is-loading');

        fetch(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            signal: controller ? controller.signal : undefined
        })
            .then(function (response) {
                if (!response.ok) throw new Error('비교 결과를 불러오지 못했습니다.');
                return response.text();
            })
            .then(function (html) {
                if (requestId !== requestSerial) return;
                var documentCopy = new DOMParser().parseFromString(html, 'text/html');
                var nextSection = documentCopy.querySelector('[data-compare-results]');
                if (!nextSection) throw new Error('비교 결과 영역을 찾지 못했습니다.');

                currentSection.replaceWith(nextSection);
                if (!options || !options.fromHistory) {
                    window.history.pushState({ comparePage: true }, '', url);
                }
                window.requestAnimationFrame(function () {
                    scrollToResults(options && options.instant ? 'auto' : 'smooth');
                    var heading = nextSection.querySelector('h2');
                    if (heading) {
                        heading.setAttribute('tabindex', '-1');
                        heading.focus({ preventScroll: true });
                    }
                });
            })
            .catch(function (error) {
                if (requestId !== requestSerial || (error && error.name === 'AbortError')) return;
                window.location.assign(url);
            })
            .finally(function () {
                if (requestId !== requestSerial) return;
                activeRequest = null;
                var section = resultsSection();
                if (section) {
                    section.removeAttribute('aria-busy');
                    section.classList.remove('is-loading');
                }
            });
    }

    document.addEventListener('click', function (event) {
        var link = event.target.closest('.js-compare-page');
        if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        loadResults(link.href);
    });

    window.addEventListener('popstate', function () {
        if (!resultsSection()) return;
        loadResults(window.location.href, { fromHistory: true, instant: true });
    });

    if (window.location.hash === '#comparison-results') {
        window.requestAnimationFrame(function () { scrollToResults('auto'); });
    }
})();
