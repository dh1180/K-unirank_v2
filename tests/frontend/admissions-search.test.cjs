const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const script = fs.readFileSync(path.join(__dirname, '../../static/js/admissions-overview.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;');
function partial(query = '', { track = '', phase = '', count = 1, page = 1 } = {}) {
  return `<div class="async-results-meta" data-year="2026" data-page="${page}" data-count="${count}" data-query="${escape(query)}" data-kind="" data-track="${track}" data-phase="${phase}"></div><p class="result-name">${escape(query || 'initial results')}</p>`;
}

async function setup(t, { mobile = false, content = partial() } = {}) {
  const filters = [['kind', ['', 'four', 'college']], ['phase', ['', 'SUSI', 'JEONGSI']], ['track', ['', 'student', 'csat']]]
    .flatMap(([name, values]) => values.map(value => `<a href="?${name}=${value}" class="js-async-filter" data-filter="${name}" data-value="${value}">${name}:${value}</a>`)).join('');
  const dom = new JSDOM(`<div class="home-discovery"><form class="home-hero-search"><input name="q"></form><section id="admission-explorer" data-selected-year="2026" data-results-url="/admissions/results/">
    <form id="admission-async-search"><input id="admission-search-input" name="q"><input name="kind"><input name="phase"><input name="track"><select id="admission-year" name="year"><option value="2026">2026</option></select></form>
    ${filters}<a id="admission-filter-reset" href="/">reset</a><span id="async-result-count">1건</span><div id="admission-search-status"></div><div id="admission-search-error" hidden></div><button id="admission-search-retry">retry</button><div id="admission-results-region">${content}</div></section></div>`, { url: 'https://example.test/', runScripts: 'outside-only' });
  const { window } = dom;
  t.after(() => window.close());
  window.matchMedia = query => ({ matches: mobile && query.includes('max-width'), addEventListener() {} });
  window.HTMLElement.prototype.scrollIntoView = () => {};
  const requests = [];
  window.fetch = (url, options) => new Promise((resolve, reject) => requests.push({ url, options, resolve, reject }));
  window.eval(script);
  await new Promise(resolve => window.addEventListener('DOMContentLoaded', resolve, { once: true }));
  const $ = selector => window.document.querySelector(selector);
  const submit = query => {
    $('#admission-search-input').value = query;
    $('#admission-async-search').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  };
  const finish = async (index, html) => {
    requests[index].resolve({ ok: true, text: async () => html });
    await tick();
  };
  return { window, $, requests, submit, finish };
}

test('late response bodies cannot overwrite a newer search or clear its busy state', async t => {
  const { $, requests, submit, finish } = await setup(t);
  submit('old');
  let finishOldBody;
  requests[0].resolve({ ok: true, text: () => new Promise(resolve => { finishOldBody = resolve; }) });
  await tick();
  submit('new');
  finishOldBody(partial('old'));
  await tick();
  assert.equal($('.result-name').textContent, 'initial results');
  assert.equal($('#admission-results-region').getAttribute('aria-busy'), 'true');
  await finish(1, partial('new', { count: 7 }));
  assert.equal($('.result-name').textContent, 'new');
  assert.equal($('#async-result-count').textContent, '7건');
  assert.equal($('#admission-results-region').getAttribute('aria-busy'), 'false');
});

test('Korean composition does not search until composition ends', async t => {
  const { window, $, requests } = await setup(t);
  const input = $('#admission-search-input');
  input.dispatchEvent(new window.CompositionEvent('compositionstart'));
  input.value = '컴퓨터';
  input.dispatchEvent(new window.Event('input'));
  await new Promise(resolve => setTimeout(resolve, 380));
  assert.equal(requests.length, 0);
  input.dispatchEvent(new window.CompositionEvent('compositionend'));
  input.dispatchEvent(new window.Event('input'));
  await new Promise(resolve => setTimeout(resolve, 380));
  assert.equal(requests.length, 1);
  assert.equal(new URL(requests[0].url, window.location.href).searchParams.get('q'), '컴퓨터');
});

test('editing a query invalidates the previous request before debounce fires', async t => {
  const { window, $, submit, finish } = await setup(t);
  submit('old');
  $('#admission-search-input').value = 'new';
  $('#admission-search-input').dispatchEvent(new window.Event('input'));
  await finish(0, partial('old'));
  assert.equal($('.result-name').textContent, 'initial results');
  assert.equal($('#admission-search-input').value, 'new');
});

test('failed searches preserve results and retry the current query', async t => {
  const { $, requests, submit, finish } = await setup(t);
  submit('간호');
  requests[0].resolve({ ok: false });
  await tick();
  assert.equal($('.result-name').textContent, 'initial results');
  assert.equal($('#admission-search-error').hidden, false);
  $('#admission-search-retry').click();
  assert.equal(requests[1].url, requests[0].url);
  await finish(1, partial('간호'));
  assert.equal($('.result-name').textContent, '간호');
  assert.equal($('#admission-search-error').hidden, true);
});

test('back restores query controls and results without adding a history entry', async t => {
  const { window, $, requests, submit, finish } = await setup(t);
  submit('컴퓨터'); await finish(0, partial('컴퓨터'));
  submit('간호'); await finish(1, partial('간호'));
  const length = window.history.length;
  const popped = new Promise(resolve => window.addEventListener('popstate', resolve, { once: true }));
  window.history.back(); await popped;
  assert.equal($('#admission-search-input').value, '컴퓨터');
  assert.equal(requests.length, 3);
  await finish(2, partial('컴퓨터'));
  assert.equal($('.result-name').textContent, '컴퓨터');
  assert.equal(window.history.length, length);
});

test('switching from coursework to regular admission clears the conflicting track', async t => {
  const { window, $, requests, finish } = await setup(t);
  $('[data-filter="track"][data-value="student"]').click();
  let params = new URL(requests[0].url, window.location.href).searchParams;
  assert.equal(params.get('phase'), 'SUSI');
  await finish(0, partial('', { track: 'student', phase: 'SUSI' }));
  $('[data-filter="phase"][data-value="JEONGSI"]').click();
  params = new URL(requests[1].url, window.location.href).searchParams;
  assert.equal(params.get('phase'), 'JEONGSI');
  assert.equal(params.has('track'), false);
  assert.equal($('[name="track"]').value, '');
});

test('mobile college results show the published average instead of an empty cutoff', async t => {
  const collegeRow = `<div class="admissions-table-wrap"><table><tbody><tr>
    <td data-label="대학"><a class="table-school-link" href="/university/1">Test College</a></td>
    <td data-label="구분">수시</td><td data-label="전형">일반전형</td><td data-label="모집단위"><a class="unit-name" href="/unit/1">간호학과</a></td>
    <td data-label="모집인원">20</td><td data-label="경쟁률">5 : 1</td>
    <td data-label="대표 지표"><span class="metric-item"><span class="metric-label">학생부 합격자 평균</span><strong class="metric-value">3.40 등급</strong></span></td>
    <td data-label="출처"><a href="https://example.com">원문</a></td>
    </tr></tbody></table></div>`;
  const { $ } = await setup(t, { mobile: true, content: partial() + collegeRow });
  assert.equal($('.mobile-cut-item b').textContent, '평균');
  assert.equal($('.mobile-cut-item strong').textContent, '3.40');
  assert.equal($('.mobile-cut-item small').textContent, '등급');
  assert.equal($('.mobile-result-university').getAttribute('href'), 'https://example.test/university/1');
  assert.equal($('.mobile-result-unit').getAttribute('href'), '/unit/1');
});
