const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const script = fs.readFileSync(
  path.join(__dirname, '../../static/js/support-school-search.js'), 'utf8'
);

function setup(t) {
  const dom = new JSDOM(
    `<label for="support-university-search">대학 검색</label>
    <input id="support-university-search" type="search">
    <span id="support-search-status"></span>
    <select id="id_university" name="university">
      <option value="">대학교 선택</option>
      <option value="2">가람대학교</option>
      <option value="3">나래대학교</option>
      <option value="4">부산대학교</option>
      <option value="5">한빛대학교</option>
    </select>`,
    { url: 'https://example.test/support/', runScripts: 'outside-only' }
  );
  t.after(() => dom.window.close());
  dom.window.eval(script);
  dom.window.document.dispatchEvent(new dom.window.Event('DOMContentLoaded'));
  return dom.window;
}

test('search filters university options without losing native select', t => {
  const window = setup(t);
  const input = window.document.querySelector('#support-university-search');
  const select = window.document.querySelector('#id_university');
  input.value = '나래';
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
  assert.deepEqual(Array.from(select.options).map(option => option.textContent),
    ['대학교 선택', '나래대학교']);
  assert.equal(window.document.querySelector('#support-search-status').textContent,
    '1개 대학 검색됨 · 아래 목록에서 선택하세요.');
  select.value = '3';
  input.value = '';
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
  assert.equal(select.value, '3');
  assert.equal(select.options.length, 5);
});

test('search ignores spaces and casing and handles no results', t => {
  const window = setup(t);
  const input = window.document.querySelector('#support-university-search');
  const select = window.document.querySelector('#id_university');
  input.value = '부 산';
  input.dispatchEvent(new window.Event('input'));
  assert.equal(select.options.length, 2);
  assert.equal(select.options[1].textContent, '부산대학교');
  input.value = '존재하지않는대학';
  input.dispatchEvent(new window.Event('input'));
  assert.equal(select.value, '');
  assert.equal(select.options.length, 1);
  assert.match(window.document.querySelector('#support-search-status').textContent,
    /검색 결과가 없습니다/);
});
