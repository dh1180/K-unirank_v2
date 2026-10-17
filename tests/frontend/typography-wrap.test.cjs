const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = path.join(__dirname, '../..');
const base = fs.readFileSync(path.join(root, 'templates/base.html'), 'utf8');
const css = fs.readFileSync(path.join(root, 'static/css/typography-wrap.css'), 'utf8');

test('all Django templates inherit site-wide Korean word boundaries from body', () => {
  assert.match(base, /<body class="kuni-design">/);
  assert.match(css, /\.kuni-design\s*\{\s*word-break:\s*keep-all;/);
  assert.match(css, /overflow-wrap:\s*break-word/);
  assert.ok(base.indexOf('css/typography-wrap.css') > base.indexOf('css/site-design.css'));
  assert.ok(base.indexOf('css/typography-wrap.css') > base.indexOf('{% block extra_head %}'));
});

test('representative admission, ranking and mobile labels opt out of single-line truncation', () => {
  for (const className of [
    'school-name', 'school-card strong', 'favorite-card-title strong',
    'result-school-name', 'admission-rank-university strong',
    'indicator-rank-university strong', 'compare-chart-school a',
    'compare-school-link', 'mobile-result-university',
    'mobile-result-unit', 'mobile-result-selection',
    'table-school-link'
  ]) {
    assert.ok(css.includes('.' + className), 'missing override for ' + className);
  }
  assert.match(css, /text-overflow:\s*clip/);
  assert.match(css, /white-space:\s*normal/);
  assert.match(css, /\.mobile-result-meta,[\s\S]*?\.mobile-result-bottom\s*\{[\s\S]*?flex-wrap:\s*wrap/);
});

test('CSS handles ordinary Korean word wrapping without forcing split-every-character', () => {
  const dom = new JSDOM(
    '<body class="kuni-design"><div class="school-name">한국 항공 우주 대학교</div></body>',
    { runScripts: 'outside-only' }
  );
  const style = dom.window.document.createElement('style');
  style.textContent = css;
  dom.window.document.head.appendChild(style);
  const name = dom.window.document.querySelector('.school-name');
  const computed = dom.window.getComputedStyle(name);
  assert.equal(computed.wordBreak, 'keep-all');
  assert.equal(computed.whiteSpace, 'normal');
  assert.equal(computed.textOverflow, 'clip');
  dom.window.close();
});
