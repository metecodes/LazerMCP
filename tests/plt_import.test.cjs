const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
const page=await browser.newPage({viewport:{width:1440,height:1000}});let calls=0;const errors=[];page.on('pageerror',e=>errors.push(e.message));
const imported=JSON.parse(fs.readFileSync('scratch/plt-fixture.json','utf8'));
await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.hostname!=='editor.test')return route.abort();
if(u.pathname==='/api/cad/design'){calls++;const data=route.request().postDataJSON();assert(data.plt.includes('PD'));assert.equal(data.parameters.format,'both');if(calls===2)return route.fulfill({json:{success:false,look_again:['Unsupported PLT instruction PE']}});return route.fulfill({json:{success:true,file_id:'imported.svg',final_status:'PROTOTYPE READY',review:{final_status:'PROTOTYPE READY'}}});}
if(u.pathname.startsWith('/api/editor/'))return route.fulfill({json:u.pathname.endsWith('/imported.svg')?imported:{...imported,name:'Mevcut çizim'}});
const f=u.pathname.startsWith('/out/')?'web/editor.html':'web'+u.pathname;return fs.existsSync(f)?route.fulfill({path:f}):route.abort();});
await page.goto('http://editor.test/out/start.svg');await page.waitForFunction(()=>document.querySelector('#save-state').textContent==='Kayıtlı');
await page.locator('#plt-file').setInputFiles({name:'house.plt',mimeType:'application/octet-stream',buffer:Buffer.from('IN;PU0,0;PD400,0,400,400,0,400,0,0;PU;')});
await page.waitForURL('**/edit/imported.svg');await page.waitForFunction(()=>document.querySelector('#note').textContent.includes('PLT çizimi açıldı'));
assert(await page.locator('#canvas path').count()>0);assert.equal(await page.locator('#assembled-view').isDisabled(),true);assert.equal(await page.locator('#download').getAttribute('aria-disabled'),'false');
await page.screenshot({path:'scratch/plt-preview.png'});
await page.locator('#plt-file').setInputFiles({name:'bad.plt',mimeType:'application/octet-stream',buffer:Buffer.from('PE;PD400,0;')});
await page.waitForFunction(()=>document.querySelector('#note').textContent.includes('Unsupported PLT'));
assert(page.url().endsWith('/edit/imported.svg'));assert(await page.locator('#canvas path').count()>0);assert.deepEqual(errors,[]);
console.log('PASS: PLT file upload, independent SVG preview, download, unsupported commands retain current drawing, no browser errors');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
