const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:1280,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.hostname!=='model.test')return route.abort();const f=u.pathname.startsWith('/models/')?'web/house-pencil-holder.html':'web'+u.pathname;return fs.existsSync(f)?route.fulfill({path:f}):route.abort();});
 await page.goto('http://model.test/models/house-pencil-holder');
 await page.waitForFunction(()=>[...document.images].every(i=>i.complete&&i.naturalWidth>0));
 assert.equal(await page.locator('a[download]').count(),2);
 await page.screenshot({path:'scratch/standard-house-page.png',fullPage:true});
 for(const width of [1280,390]){await page.setViewportSize({width,height:1050});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
 assert.deepEqual(errors,[]);console.log('PASS: permanent model page, real SVG previews, downloads, responsive layout');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
