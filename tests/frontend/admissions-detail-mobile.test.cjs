const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const script = fs.readFileSync(
  path.join(__dirname, '../../static/js/admissions-detail-mobile.js'),
  'utf8'
);

function createUniversityMarkup() {
  return `
    <div class="admissions-table-wrap">
      <table>
        <thead>
          <tr>
            <th>학년도</th>
            <th>구분</th>
            <th>전형</th>
            <th>모집단위</th>
            <th>모집</th>
            <th>경쟁률</th>
            <th>공개 지표</th>
            <th>출처</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td data-label="학년도">2026</td>
            <td data-label="구분"><span class="phase-badge jeongsi">정시</span></td>
            <td data-label="전형"><strong>수능</strong><br><small class="subtle">일반전형</small></td>
            <td data-label="모집단위">
              <div class="favorite-unit-line">
                <strong class="unit-name">항공우주공학과</strong>
              </div>
            </td>
            <td data-label="모집">25</td>
            <td data-label="경쟁률">4.50 : 1</td>
            <td data-label="공개 지표" class="metrics-cell">
              <div class="metric-stack">
                <span class="metric-item">
                  <span class="metric-label">공식 평균 백분위 70% 컷</span>
                  <strong class="metric-value">85.50</strong>
                </span>
              </div>
            </td>
            <td data-label="출처"><a class="source-link" href="https://example.com/source">원문 ↗</a></td>
          </tr>
        </tbody>
      </table>
    </div>
  `;
}

function createRecruitmentUnitMarkup() {
  return `
    <div class="admissions-table-wrap">
      <table>
        <thead>
          <tr>
            <th>학년도</th>
            <th>구분</th>
            <th>전형</th>
            <th>모집인원</th>
            <th>경쟁률</th>
            <th>공개 지표</th>
            <th>출처</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td data-label="학년도">2026</td>
            <td data-label="구분"><span class="phase-badge susi">수시</span></td>
            <td data-label="전형"><strong>학생부교과</strong><br><small class="subtle">학교장추천</small></td>
            <td data-label="모집인원">14명</td>
            <td data-label="경쟁률">3.20 : 1</td>
            <td data-label="공개 지표" class="metrics-cell">
              <div class="metric-stack">
                <span class="metric-item">
                  <span class="metric-label">학생부등급 70% 컷</span>
                  <strong class="metric-value">2.15<small>등급</small></strong>
                </span>
              </div>
            </td>
            <td data-label="출처"><a class="source-link" href="https://example.com/source">대입정보포털 어디가 ↗</a></td>
          </tr>
        </tbody>
      </table>
    </div>
  `;
}

function setupDom(html, { mobile = true } = {}) {
  const dom = new JSDOM(
    `<!doctype html><html><head></head><body>${html}</body></html>`,
    { url: 'https://k-unirank.com/admissions/' }
  );
  const { window } = dom;
  window.matchMedia = query => ({
    matches: mobile && query.includes('max-width'),
    addEventListener() {},
    addListener() {},
    removeEventListener() {},
    removeListener() {}
  });

  const run = new Function('window', 'document', script);
  run(window, window.document);
  if (window.document.readyState === 'loading') {
    window.document.dispatchEvent(new window.Event('DOMContentLoaded'));
  }
  return { dom, window, document: window.document };
}

test('mobile: university detail table compacts rows with recruitment unit title and details', () => {
  const { document, window } = setupDom(createUniversityMarkup(), { mobile: true });

  const compact = document.querySelector('.mobile-admission-compact');
  assert.ok(compact, 'compact cell should be created');

  const unit = compact.querySelector('.mobile-result-unit');
  assert.equal(unit.textContent.trim(), '항공우주공학과');

  const selection = compact.querySelector('.mobile-result-selection');
  assert.equal(selection.textContent.trim(), '수능 · 일반전형');

  const cut = compact.querySelector('.mobile-cut-item');
  assert.ok(cut.textContent.includes('70%'));
  assert.ok(cut.textContent.includes('85.50'));

  const bottom = compact.querySelector('.mobile-result-bottom');
  assert.ok(bottom.textContent.includes('모집 25명'));
  assert.ok(bottom.textContent.includes('경쟁률 4.50 : 1'));

  const source = compact.querySelector('.mobile-source-link');
  assert.equal(source.getAttribute('href'), 'https://example.com/source');

  const wrap = document.querySelector('.admissions-table-wrap');
  assert.ok(wrap.classList.contains('has-mobile-compact'));

  window.close();
});

test('mobile: recruitment unit detail table (no unit column, 모집인원 label) compacts correctly', () => {
  const { document, window } = setupDom(createRecruitmentUnitMarkup(), { mobile: true });

  const compact = document.querySelector('.mobile-admission-compact');
  assert.ok(compact, 'compact cell should be created for recruitment unit table');

  const unit = compact.querySelector('.mobile-result-unit');
  assert.equal(unit.textContent.trim(), '학생부교과', 'selection category should be primary title when unit column is absent');

  const selection = compact.querySelector('.mobile-result-selection');
  assert.equal(selection.textContent.trim(), '학교장추천', 'selection subtitle should contain details');

  const cut = compact.querySelector('.mobile-cut-item');
  assert.ok(cut.textContent.includes('70%'));
  assert.ok(cut.textContent.includes('2.15'));

  const bottom = compact.querySelector('.mobile-result-bottom');
  assert.ok(bottom.textContent.includes('모집 14명'), 'recruitment count with 명 should be formatted cleanly');
  assert.ok(bottom.textContent.includes('경쟁률 3.20 : 1'));

  const source = compact.querySelector('.mobile-source-link');
  assert.equal(source.getAttribute('href'), 'https://example.com/source');

  const wrap = document.querySelector('.admissions-table-wrap');
  assert.ok(wrap.classList.contains('has-mobile-compact'));

  window.close();
});

test('desktop: does not generate compact card and applies metric refinement', () => {
  const { document, window } = setupDom(createRecruitmentUnitMarkup(), { mobile: false });

  const compact = document.querySelector('.mobile-admission-compact');
  assert.equal(compact, null, 'no compact cell on desktop');

  const featured = document.querySelector('.metric-item-featured');
  assert.ok(featured, 'desktop metrics should be highlighted');
  assert.ok(featured.classList.contains('metric-item-featured-grade'));

  window.close();
});

test('metric checkbox submits all results and restores the default filtered view', () => {
  const controls = `
    <form id="university-metric-filter-form">
      <input id="university-metrics-view" name="metrics" value="all" disabled>
      <input id="university-metrics-only" type="checkbox" checked>
    </form>`;
  const { document, window } = setupDom(controls, { mobile: false });
  const form = document.getElementById('university-metric-filter-form');
  const field = document.getElementById('university-metrics-view');
  const toggle = document.getElementById('university-metrics-only');
  let submissions = 0;
  form.addEventListener('submit', event => {
    event.preventDefault();
    submissions += 1;
  });

  toggle.checked = false;
  toggle.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(field.disabled, false);
  assert.equal(submissions, 1);

  toggle.checked = true;
  toggle.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(field.disabled, true);
  assert.equal(submissions, 2);

  window.close();
});
