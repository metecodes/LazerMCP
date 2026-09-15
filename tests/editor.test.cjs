const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
 const run = require('node:child_process').spawnSync(process.env.PYTHON || (process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python'), ['tests/editor_fixture.py'], {encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);
 const fixture=JSON.parse(run.stdout);
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1600,height:1000}});
 const errors=[];let submitted;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.hostname!=='editor.test')return route.abort();
  if(url.pathname.endsWith('/preview')){submitted=route.request().postDataJSON();return route.fulfill({json:fixture.preview});}
  if(url.pathname.endsWith('/save')){submitted=route.request().postDataJSON();fixture.meta.primitives=submitted.primitives;fixture.meta.parameters=submitted.parameters;fixture.meta.version++;return route.fulfill({json:{success:true,file_id:'saved.svg'}});}
  if(url.pathname.endsWith('/history'))return route.fulfill({json:{success:true,versions:[{n:1,primitives:fixture.meta.primitives,parameters:fixture.meta.parameters}]}});
  if(url.pathname.startsWith('/api/editor/'))return route.fulfill({json:fixture.meta});
  if(url.pathname.startsWith('/files/'))return route.fulfill({contentType:'image/svg+xml',body:fixture.preview.svg});
  const file=url.pathname.startsWith('/edit/')?'web/editor.html':'web'+url.pathname;
  if(fs.existsSync(file))return route.fulfill({path:file});return route.abort();
 });
 await page.goto('http://editor.test/edit/test.svg');await page.locator('#canvas svg').waitFor();
 assert.equal(await page.locator('.part').count(),2);
 assert(Number(await page.locator('[data-selection] rect').getAttribute('width'))>100);
 await page.fill('#search','Destek');assert.equal(await page.locator('.part').count(),1);await page.fill('#search','');
 await page.locator('.part').first().locator('.mini').nth(1).click();await page.fill('#width','130');await page.click('#apply');assert.match(await page.locator('#note').innerText(),/kilitli/);await page.locator('.part').first().locator('.mini').nth(1).click();
 await page.fill('#width','130');await page.click('#apply');assert.equal(await page.locator('#save-state').innerText(),'Kaydedilmedi');await page.click('#undo');assert.equal(await page.inputValue('#width'),'120');await page.click('#redo');assert.equal(await page.inputValue('#width'),'130');
 await page.fill('#hole-x','1');await page.click('#add-hole');assert.match(await page.locator('#note').innerText(),/içinde/);
 await page.fill('#hole-x','30');await page.fill('#hole-y','25');await page.click('#add-hole');
 await page.click('#validate');await page.waitForFunction(()=>document.querySelector('#save-state').textContent!=='İşleniyor…');assert.equal(submitted.primitives[0].slots.at(-1).x,30);
 await page.click('#place-hole');await page.locator('#canvas svg').click();assert(Number(await page.inputValue('#hole-x'))>0);
 await page.click('#zoom-in');assert.equal(await page.locator('#zoom').innerText(),'125%');await page.click('#fit');
 await page.click('#add-part');await page.fill('#new-name','Yeni panel');await page.click('#new-part-form button[type=submit], #new-part-form .cut');assert.equal(await page.locator('.part').count(),3);
 await page.click('#connections-tab');await page.selectOption('#connection-a',fixture.meta.primitives[0].label);await page.selectOption('#connection-b','Destek');await page.click('#connect');assert.match(await page.locator('#note').innerText(),/eşleşmiyor/);
 await page.click('#properties-tab');await page.selectOption('#part','0');await page.fill('#width','120');await page.click('#apply');await page.click('#connections-tab');await page.click('#connect');assert.equal(await page.locator('.connection-row').count(),1);
 await page.click('#save');await page.waitForURL('**/edit/saved.svg');await page.waitForFunction(()=>document.querySelector('#save-state').textContent==='Kayıtlı');assert.equal(submitted.parameters.editor_connections.length,1);
 await page.locator('summary').click();await page.click('#history-load');await page.locator('.history-row button').click();
 for(const width of [1600,768,390]){await page.setViewportSize({width,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow ${width}`);}
 await page.setViewportSize({width:1600,height:1000});await page.click('#properties-tab');await page.screenshot({path:'editor-preview.png',fullPage:true});
 assert.deepEqual(errors,[]);await browser.close();console.log('PASS: search, lock, dimensions, undo/redo, hole validation, position picker, zoom, new part, connections, save, history, responsive layout');
})().catch(e=>{console.error(e);process.exit(1);});

