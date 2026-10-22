// Smoke tests for the single-file worker (edge/worker.js). Run with: npm test
import assert from 'node:assert/strict';
import { test } from 'node:test';

import worker from '../worker.js';

const ROW = {
  guest_name: 'Rahul Sharma & Family',
  custom_note: null,
  template_id: 'missing-design',
  couple_names: 'Aarav & Priya',
  event_date: 'December 25, 2026',
  venue: 'Taj Lands End',
};

const dbReturning = (row) => ({
  prepare: () => ({ bind: (...params) => ({ first: async () => (params[1] === 'rahul' ? row : null) }) }),
});
const get = (path, init) => new Request(`https://invites.example.com${path}`, init);

test('single-file worker renders a known guest and falls back to the base template', async () => {
  const response = await worker.fetch(get('/aarav-and-priya/to/rahul/'), { DB: dbReturning(ROW) });
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.ok(html.includes('Rahul Sharma &amp; Family'));
  assert.ok(html.includes("We can't wait to celebrate"));
  assert.doesNotMatch(html, /\{\{\s*[A-Z_]+\s*\}\}/);
});

test('single-file worker returns a clean 404 for unknown guests and other paths', async () => {
  for (const path of ['/aarav-and-priya/to/stranger', '/', '/x/to/y/z']) {
    const response = await worker.fetch(get(path), { DB: dbReturning(ROW) });
    assert.equal(response.status, 404, path);
    assert.match(await response.text(), /Invitation not found/);
  }
});

test('single-file worker escapes guest data and rejects non-GET methods', async () => {
  const hostile = { ...ROW, guest_name: '<script>alert(1)</script>' };
  const html = await (await worker.fetch(get('/a/to/rahul'), { DB: dbReturning(hostile) })).text();
  assert.ok(!html.includes('<script>alert(1)'));
  assert.equal((await worker.fetch(get('/a/to/rahul', { method: 'POST' }), { DB: dbReturning(ROW) })).status, 405);
});

test('single-file worker turns database errors into a 500', async () => {
  const brokenDb = { prepare: () => ({ bind: () => ({ first: async () => { throw new Error('D1 down'); } }) }) };
  assert.equal((await worker.fetch(get('/a/to/rahul'), { DB: brokenDb })).status, 500);
});
