const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const data=JSON.parse(fs.readFileSync('scratch/house-fixture.json','utf8'));
await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.hostname!=='editor.test')return route.abort();if(u.pathname.startsWith('/api/editor/'))return route.fulfill({json:data});const f=u.pathname.startsWith('/out/')?'web/editor.html':'web'+u.pathname;return fs.existsSync(f)?route.fulfill({path:f}):route.abort();});
await page.goto('http://editor.test/out/house.svg');await page.waitForFunction(()=>document.querySelector('#save-state').textContent==='Kayıtlı');
await page.click('#assembled-view');assert.equal(await page.locator('#canvas svg [data-panel]').count(),7);await page.screenshot({path:'scratch/house-assembled.png'});
await page.click('#cut-view');assert.equal(await page.locator('#cut-view').getAttribute('aria-pressed'),'true');
await page.click('#assembled-view');await page.click('#zoom-in');assert.match(await page.locator('#lede').innerText(),/Dik monte/);
assert.deepEqual(errors,[]);console.log('PASS: six structural panels plus a raised star, upright preview, cutting view switch, no browser errors');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
