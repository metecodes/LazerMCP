// Studio page in a real browser with stubbed APIs: save-vs-preview race, escaped history,
// reopening a saved file (form + chat restore, same project), and readable HTTP errors.
// Needs Playwright + Edge (set PLAYWRIGHT_MODULE to an installed module path if needed).
// three.js is loaded from its CDN, so the machine needs network access.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const ROOT = path.resolve(__dirname, '..');
const ASSEMBLY = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'studio_box_assembly.json'), 'utf8'));
const EVIL = '<img src=x onerror="window.__xss=1">';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function openStudio(browser, {query = '', boxFails = false, aiReply = null} = {}) {
  const page = await browser.newPage({acceptDownloads: true});
  const seen = {box: []};
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('**/*', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (url.hostname === 'cdn.jsdelivr.net') return route.continue();
    if (url.hostname !== 'studio.test') return route.abort();
    const p = url.pathname;
    if (p === '/studio') return route.fulfill({path: path.join(ROOT, 'web', 'studio.html'), contentType: 'text/html'});
    if (p === '/api/account') return route.fulfill({json: {user: {email: 'maker@studio.test'}, access_ready: true}});
    if (p === '/api/plans') return route.fulfill({json: {plans: []}});
    if (p === '/api/studio/profiles') return route.fulfill({json: {materials: [], machines: []}});
    if (p === '/api/studio/projects') {
      if (url.searchParams.get('project_id')) return route.fulfill({json: {success: true, project: {versions: [{n: 1, file_id: EVIL}]}}});
      return route.fulfill({json: {success: true, projects: [{id: 'proj-1', name: EVIL, latest: {n: 1, final_status: EVIL}},
        {id: 'proj-2', name: 'eski kutu', latest: {n: 3, final_status: 'BLOCKED'}}]}});
    }
    if (p === '/api/studio/box') {
      const body = JSON.parse(req.postData() || '{}');
      seen.box.push(body);
      if (body.preview) return route.fulfill({json: {success: true, preview: true, gate_skipped: true, assembly: ASSEMBLY, summary: {}}});
      if (boxFails) return route.fulfill({status: 500, body: 'boom'});
      await sleep(400); // slower than the live-preview debounce
      return route.fulfill({json: {success: true, export_allowed: true, final_status: 'PROTOTYPE READY', file_id: 'saved.svg', project: {project_id: 'proj-1'}, assembly: ASSEMBLY}});
    }
    if (p === '/api/studio/ai' && aiReply) return route.fulfill({json: aiReply});
    if (p.startsWith('/api/assembly/')) {
      return route.fulfill({json: {...ASSEMBLY, success: true, file_id: 'old.svg', project_id: 'proj-1',
        studio_form: {x: '222', y: '111', h: '55', lid: 'open', dividers_x: '2'},
        studio_chat: [{role: 'user', text: 'kalemlik yap'}, {role: 'assistant', text: 'Hazır'}]}});
    }
    if (p.startsWith('/files/')) return route.fulfill({body: '<svg xmlns="http://www.w3.org/2000/svg"/>', contentType: 'image/svg+xml'});
    if (p.startsWith('/api/')) return route.fulfill({json: {success: true}});
    const file = path.join(ROOT, 'web', p.replace(/^\//, ''));
    return fs.existsSync(file) ? route.fulfill({path: file}) : route.abort();
  });
  await page.goto('http://studio.test/studio' + query);
  await page.waitForFunction(() => /Önizleme|Açıldı|Hazır/.test(document.querySelector('#status').textContent), null, {timeout: 30000});
  return {page, seen, errors};
}

(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    // 1. Editing then saving at once: the save must not be swallowed by the pending preview.
    {
      const {page, seen, errors} = await openStudio(browser);
      const before = seen.box.length;
      await page.fill('#box-x', '190'); // input event schedules a live preview
      const download = page.waitForEvent('download', {timeout: 10000});
      await page.click('#make-box');
      await download;
      await sleep(600);
      const after = seen.box.slice(before);
      assert.equal(after.filter((b) => !b.preview).length, 1, 'one save request');
      assert.equal(after.filter((b) => b.preview).length, 0, 'no preview fired after the save click');
      assert.equal(after[0].x, 190);
      assert.equal(after[0].studio_form.x, '190', 'form travels with the save');
      assert.match(await page.locator('#status').innerText(), /Kayıtlı/);
      assert.equal(await page.locator('#dl-svg').getAttribute('href'), '/files/saved.svg?download=1');

      // 2. Project names and versions from the server are text, never markup.
      await page.click('.tabs button[data-tab="history"]');
      await page.locator('#hist-list li strong').first().waitFor();
      assert.equal(await page.locator('#hist-list li strong').first().innerText(), EVIL);
      assert.equal(await page.locator('#hist-list img').count(), 0);
      await page.locator('#hist-list li').first().click();
      await page.locator('#hist-versions li').first().waitFor();
      assert.equal(await page.locator('#hist-versions img').count(), 0);
      assert.equal(await page.evaluate(() => window.__xss), undefined);
      assert.deepEqual(errors, []);
      await page.close();
    }
    // 3. Reopening a saved file restores its form and chat, and the next save versions it.
    {
      const {page, seen, errors} = await openStudio(browser, {query: '?file=old.svg'});
      assert.equal(await page.inputValue('#box-x'), '222');
      assert.equal(await page.inputValue('#box-dx'), '2');
      assert.match(await page.locator('#status').innerText(), /form bu dosyanın ölçüleriyle/);
      assert.match(await page.locator('#ai-chat-log').innerText(), /kalemlik yap/);
      const download = page.waitForEvent('download', {timeout: 10000});
      await page.click('#make-box');
      await download;
      const save = seen.box.filter((b) => !b.preview).pop();
      assert.equal(save.project_id, 'proj-1');
      assert.equal(save.x, 222);
      assert.deepEqual(errors, []);
      await page.close();
    }
    // 4. A failing server gives a readable message instead of a silent stop.
    {
      const {page, errors} = await openStudio(browser, {boxFails: true});
      await page.click('#make-box');
      await page.waitForFunction(() => /Sunucu/.test(document.querySelector('#status').textContent), null, {timeout: 10000});
      assert.equal(await page.locator('#make-box').isDisabled(), false);
      assert.deepEqual(errors, []);
      await page.close();
    }
    // 5. AI: a draft the gate blocked but auto-repair fixed reads as "found it, fixed it".
    const runAi = async (aiReply) => {
      const {page, errors} = await openStudio(browser, {aiReply});
      await page.click('.tabs button[data-tab="ai"]');
      await page.fill('#ai-prompt', 'telefon standı');
      await page.click('#make-ai');
      await page.waitForFunction(() => !document.querySelector('#make-ai').disabled && /Hazır|düzelt|kontrol/i.test(document.querySelector('#status').textContent));
      return {page, errors};
    };
    const base = {success: true, source: 'prompt_llm', assembly: ASSEMBLY, plan_job: {summary: 'Telefon standı, 3 parça'}};
    {
      const {page, errors} = await runAi({...base, ok: true, export_allowed: true, final_status: 'PROTOTYPE READY', file_id: 'ai.svg',
        auto_repair: {attempted: 1, fixed: true, issues: ['edge f has no F partner', 'slot overlaps hole']},
        look_again: ['Auto-repair: the first draft had 2 gate issue(s); fixed automatically.']});
      assert.match(await page.locator('#status').innerText(), /2 sorun bulduk ve otomatik düzelttik/);
      assert.match(await page.locator('#ai-chat-log').innerText(), /otomatik düzelttik/);
      assert(await page.locator('#ai-block').evaluate((el) => el.classList.contains('hide')), 'no block banner');
      assert.doesNotMatch(await page.locator('body').innerText(), /BLOCKED/);
      assert.deepEqual(errors, []);
      await page.close();
    }
    // 6. Still blocked after repair: honest (no download) but plain words, no "BLOCKED".
    {
      const {page, errors} = await runAi({...base, ok: false, export_allowed: false, final_status: 'BLOCKED', file_id: null,
        auto_repair: {attempted: 2, fixed: false, issues: ['slot overlaps hole']},
        scorecard: {final_gate: 'BLOCKED', digital: {Connections: 'FAIL', Safety: 'PASS', Assembly: 'NOT_VERIFIED'}},
        look_again: ['BLOCKED — SVG/DXF not authorized. Read the notes below, fix in chat, then retry.',
          'Auto-repair tried 2 time(s) and could not pass the gate.',
          'female edge a.right (40.0 mm) has no matching f fingers',
          'entrance role=structural has mates=[]; placement is not connection evidence',
          'ASSEMBLY is NOT VERIFIED — cannot mark PASS', 'slot overlaps hole']});
      assert.match(await page.locator('#ai-block-title').textContent(), /Otomatik düzeltme bu sefer yetmedi/);
      const blockText = await page.locator('#ai-block-text').innerText();
      assert.match(blockText, /a parçasının sağ kenarındaki diş yuvalarına \(40 mm\) geçecek karşı parça yok/);
      assert.match(blockText, /entrance parçası hiçbir parçaya bağlanmıyor/);
      assert.match(blockText, /slot overlaps hole/); // unknown notes stay as written
      assert.doesNotMatch(blockText, /NOT VERIFIED|mates=\[\]/);
      assert.match(await page.locator('#gate-score').innerText(), /1 geçmedi, 1 geçti, 1 doğrulanmadı/);
      assert.doesNotMatch(await page.locator('body').innerText(), /object Object/);
      assert.match(await page.locator('#ai-chat-log').innerText(), /2 kez otomatik düzeltmeyi denedim/);
      assert.doesNotMatch(await page.locator('body').innerText(), /BLOCKED/);
      assert.equal(await page.locator('#dl-svg').isVisible(), false);
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('PASS: save beats pending preview, escaped history, reopen restores form/chat/project, readable HTTP errors, AI auto-repair wording');
  } finally {
    await browser.close();
  }
})().catch((e) => { console.error(e); process.exit(1); });
