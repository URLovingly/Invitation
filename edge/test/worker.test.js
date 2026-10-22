// Run with: npm test   (Node 20+, no dependencies)
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import worker from '../src/index.js';
import { buildValues, escapeHtml, hydrate } from '../src/render.js';
import { matchInvitePath } from '../src/router.js';

const BASE_TEMPLATE = await readFile(fileURLToPath(new URL('../public/templates/base.html', import.meta.url)), 'utf8');

const ROW = {
  guest_name: 'Rahul Sharma & Family',
  custom_note: 'Please bless us.',
  template_id: 'base',
  couple_names: 'Aarav & Priya',
  event_date: 'December 25, 2026',
  venue: 'Taj Lands End',
};

/** Fake D1: returns `row` only for the expected slugs and records the bound values. */
function fakeDb(row, expected = ['aarav-and-priya', 'rahul-sharma-and-family']) {
  const calls = [];
  return {
    calls,
    prepare(sql) {
      return {
        bind(...params) {
          calls.push({ sql, params });
          return { first: async () => (params[0] === expected[0] && params[1] === expected[1] ? row : null) };
        },
      };
    },
  };
}

/** Fake static-asset binding serving the templates in `files` (path -> markup). */
function fakeAssets(files) {
  return { fetch: async (request) => {
    const body = files[new URL(request.url).pathname];
    return body === undefined ? new Response('missing', { status: 404 }) : new Response(body, { status: 200 });
  } };
}

const env = (overrides = {}) => ({
  DB: fakeDb(ROW),
  ASSETS: fakeAssets({ '/templates/base.html': BASE_TEMPLATE }),
  ...overrides,
});
const get = (path, init) => new Request(`https://invites.example.com${path}`, init);

// ---- router ---------------------------------------------------------------
test('router matches /:couple/to/:guest with and without trailing slash', () => {
  assert.deepEqual(matchInvitePath('/aarav-and-priya/to/rahul'), { coupleSlug: 'aarav-and-priya', guestSlug: 'rahul' });
  assert.deepEqual(matchInvitePath('/aarav-and-priya/to/rahul/'), { coupleSlug: 'aarav-and-priya', guestSlug: 'rahul' });
});

test('router lower-cases slugs', () => {
  assert.deepEqual(matchInvitePath('/Aarav-And-Priya/To/Rahul'), { coupleSlug: 'aarav-and-priya', guestSlug: 'rahul' });
});

test('router rejects other shapes and unsafe characters', () => {
  for (const path of ['/', '/aarav', '/a/b/c', '/a/to/', '//to/x', '/a/to/b/c', '/a/to/b%20c', '/a/to/b_c', '/a/to/..', '/templates/base.html']) {
    assert.equal(matchInvitePath(path), null, path);
  }
});

// ---- rendering ------------------------------------------------------------
test('escapeHtml escapes markup characters', () => {
  assert.equal(escapeHtml(`<b a="1">'&`), '&lt;b a=&quot;1&quot;&gt;&#39;&amp;');
  assert.equal(escapeHtml(null), '');
});

test('hydrate replaces placeholders, tolerates spaces and drops unknown ones', () => {
  assert.equal(hydrate('Hi {{GUEST_NAME}} / {{ COUPLE_NAMES }} / {{NOPE}}', { GUEST_NAME: 'A', COUPLE_NAMES: 'B' }), 'Hi A / B / ');
});

test('hydrate does not expand placeholders found inside values', () => {
  assert.equal(hydrate('{{GUEST_NAME}}', { GUEST_NAME: '{{COUPLE_NAMES}}', COUPLE_NAMES: 'secret' }), '{{COUPLE_NAMES}}');
});

test('buildValues falls back to friendly defaults', () => {
  const values = buildValues({ guest_name: 'G', couple_names: 'C', custom_note: '  ', event_date: null, venue: undefined });
  assert.match(values.CUSTOM_NOTE, /celebrate/);
  assert.equal(values.EVENT_DATE, 'Details to follow');
  assert.equal(values.VENUE, 'Venue to be announced');
});

// ---- worker ---------------------------------------------------------------
test('known guest returns 200 with the placeholders filled in', async () => {
  const response = await worker.fetch(get('/aarav-and-priya/to/rahul-sharma-and-family/'), env());
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /text\/html/);
  const html = await response.text();
  assert.ok(html.includes('Rahul Sharma &amp; Family'));
  assert.ok(html.includes('Aarav &amp; Priya'));
  assert.ok(html.includes('Please bless us.'));
  assert.ok(html.includes('December 25, 2026'));
  assert.doesNotMatch(html, /\{\{\s*[A-Z_]+\s*\}\}/);
});

test('the database is queried with bound slugs only', async () => {
  const db = fakeDb(ROW);
  await worker.fetch(get('/Aarav-and-Priya/to/rahul-sharma-and-family'), env({ DB: db }));
  assert.equal(db.calls.length, 1);
  assert.deepEqual(db.calls[0].params, ['aarav-and-priya', 'rahul-sharma-and-family']);
  assert.match(db.calls[0].sql, /\?1/);
});

test('unknown guest returns a clean 404 page', async () => {
  const response = await worker.fetch(get('/aarav-and-priya/to/stranger'), env());
  assert.equal(response.status, 404);
  assert.match(await response.text(), /Invitation not found/);
});

test('paths that are not invitations return 404 without touching the database', async () => {
  const db = fakeDb(ROW);
  for (const path of ['/', '/templates/base.html', '/favicon.ico']) {
    assert.equal((await worker.fetch(get(path), env({ DB: db }))).status, 404, path);
  }
  assert.equal(db.calls.length, 0);
});

test('guest data is HTML-escaped so it cannot inject markup', async () => {
  const hostile = { ...ROW, guest_name: '<script>alert(1)</script>', custom_note: '"><img src=x onerror=alert(1)>' };
  const html = await (await worker.fetch(get('/aarav-and-priya/to/rahul-sharma-and-family'), env({ DB: fakeDb(hostile) }))).text();
  assert.ok(!html.includes('<script>alert(1)'));
  assert.ok(!html.includes('<img src=x'));
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
});

test('unknown template_id falls back to the base template', async () => {
  const row = { ...ROW, template_id: 'does-not-exist' };
  const response = await worker.fetch(get('/aarav-and-priya/to/rahul-sharma-and-family'), env({ DB: fakeDb(row) }));
  assert.equal(response.status, 200);
});

test('a guest can use a different template', async () => {
  const row = { ...ROW, template_id: 'gold' };
  const assets = fakeAssets({ '/templates/base.html': BASE_TEMPLATE, '/templates/gold.html': '<p>GOLD {{GUEST_NAME}}</p>' });
  const html = await (await worker.fetch(get('/aarav-and-priya/to/rahul-sharma-and-family'), env({ DB: fakeDb(row), ASSETS: assets }))).text();
  assert.equal(html, '<p>GOLD Rahul Sharma &amp; Family</p>');
});

test('missing base template is reported as a 500, not a broken page', async () => {
  const response = await worker.fetch(get('/aarav-and-priya/to/rahul-sharma-and-family'), env({ ASSETS: fakeAssets({}) }));
  assert.equal(response.status, 500);
});

test('database errors become a 500', async () => {
  const brokenDb = { prepare: () => ({ bind: () => ({ first: async () => { throw new Error('D1 down'); } }) }) };
  const response = await worker.fetch(get('/aarav-and-priya/to/rahul-sharma-and-family'), env({ DB: brokenDb }));
  assert.equal(response.status, 500);
});

test('only GET and HEAD are allowed', async () => {
  const response = await worker.fetch(get('/aarav-and-priya/to/rahul-sharma-and-family', { method: 'POST' }), env());
  assert.equal(response.status, 405);
  assert.equal(response.headers.get('allow'), 'GET, HEAD');
});

test('security headers are present', async () => {
  const response = await worker.fetch(get('/aarav-and-priya/to/rahul-sharma-and-family'), env());
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
});
