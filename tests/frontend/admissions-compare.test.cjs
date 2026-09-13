const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const script = fs.readFileSync(
  path.join(__dirname, '../../static/js/admissions-compare.js'),
  'utf8'
);
const tick = () => new Promise(resolve => setImmediate(resolve));

function resultsPage(page, nextPage) {
  return `<section id="comparison-results" data-compare-results>
    <h2>모집단위별 비교</h2>
    <div class="pagination-center"><strong>${page}</strong></div>
    ${nextPage ? `<a class="js-compare-page" href="/?page=${nextPage}#comparison-results">다음</a>` : ''}
  </section>`;
}

test('comparison pagination replaces only the results and keeps the heading in view', async t => {
  const dom = new JSDOM(resultsPage(1, 2), {
    url: 'https://example.test/?page=1#comparison-results',
    runScripts: 'outside-only'
  });
  const { window } = dom;
  t.after(() => window.close());

  let scrollOptions = null;
  window.HTMLElement.prototype.scrollIntoView = options => { scrollOptions = options; };
  window.requestAnimationFrame = callback => callback();
  window.fetch = async () => ({ ok: true, text: async () => resultsPage(2) });

  window.eval(script);
  window.document.querySelector('.js-compare-page').dispatchEvent(
    new window.MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
  );
  await tick();
  await tick();

  assert.equal(window.document.querySelector('.pagination-center strong').textContent, '2');
  assert.equal(window.document.querySelector('#comparison-results h2').textContent, '모집단위별 비교');
  assert.equal(window.location.search, '?page=2');
  assert.equal(window.location.hash, '#comparison-results');
  assert.equal(scrollOptions.block, 'start');
  assert.equal(scrollOptions.behavior, 'smooth');
  assert.equal(window.document.activeElement.textContent, '모집단위별 비교');
});

test('a late comparison response cannot replace a newer page', async t => {
  const dom = new JSDOM(`<section id="comparison-results" data-compare-results>
      <h2>모집단위별 비교</h2>
      <a class="js-compare-page first" href="/?page=2#comparison-results">다음</a>
      <a class="js-compare-page second" href="/?page=3#comparison-results">마지막</a>
    </section>`, {
    url: 'https://example.test/?page=1#comparison-results',
    runScripts: 'outside-only'
  });
  const { window } = dom;
  t.after(() => window.close());
  window.HTMLElement.prototype.scrollIntoView = () => {};
  window.requestAnimationFrame = callback => callback();

  const requests = [];
  window.fetch = url => new Promise(resolve => requests.push({ url, resolve }));
  window.eval(script);
  window.document.querySelector('.first').click();
  window.document.querySelector('.second').click();

  requests[1].resolve({ ok: true, text: async () => resultsPage(3) });
  await tick();
  await tick();
  requests[0].resolve({ ok: true, text: async () => resultsPage(2) });
  await tick();
  await tick();

  assert.equal(window.document.querySelector('.pagination-center strong').textContent, '3');
  assert.equal(window.location.search, '?page=3');
});
