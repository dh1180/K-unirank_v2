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


def university_admissions(request, university_id):
    response = filtered_university_admissions(request, university_id)
    if response.status_code != 200 or not hasattr(response, 'content'):
        return response

    html = response.content.decode(response.charset or 'utf-8')
    if '</body>' in html:
        html = html.replace('</body>', TRACK_SCRIPT + '\n</body>', 1)
        response.content = html.encode(response.charset or 'utf-8')
    return response
