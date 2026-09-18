const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  for(const scenario of ['bundle','retry','expired','missing','signin']){
   const page=await browser.newPage(); let requests=0, svgRequests=0; const errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.hostname!=='editor.test')return route.abort();
    if(url.pathname==='/account')return route.fulfill({contentType:'text/html',body:'Giriş'});
    if(url.pathname.startsWith('/api/editor/')){
     requests++;
     if(scenario==='retry'&&requests<3)return route.fulfill({status:503,json:{success:false}});
     if(scenario==='expired')return route.fulfill({status:410,json:{success:false,look_again:['Dosyanın 24 saatlik saklama süresi doldu.']}});
     if(scenario==='missing')return route.fulfill({status:404,json:{success:false,look_again:['Dosya bulunamadı.']}});
     if(scenario==='signin')return route.fulfill({status:401,json:{success:false,signin_url:'/account?next=%2Fout%2Ftest.svg'}});
     return route.fulfill({json:{success:true,editable:true,name:'Test',primitives:[{type:'panel',label:'Panel',w:10,h:10}],parameters:{},
      svg:'<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" viewBox="0 0 10 10"><g data-panel="Panel"><rect width="10" height="10"/></g></svg>'}});
    }
    if(url.pathname.startsWith('/files/')){svgRequests++;return route.abort();}
    const file=url.pathname.startsWith('/out/')?'web/editor.html':'web'+url.pathname;
    return fs.existsSync(file)?route.fulfill({path:file}):route.abort();
   });
   await page.goto('http://editor.test/out/test.svg');
   if(scenario==='bundle'||scenario==='retry'){
    await page.locator('#canvas svg').waitFor();
    await page.waitForFunction(()=>document.querySelector('#save-state').textContent==='Kayıtlı');
    assert.equal(svgRequests,0,'bundle must avoid a second SVG request');
    assert.equal(requests,scenario==='retry'?3:1);
   }else if(scenario==='signin'){
    await page.waitForURL('**/account?next=*');
   }else{
    await page.waitForFunction(()=>document.querySelector('#save-state').textContent==='Dosya açılmadı');
    assert(!/Yükleniyor/.test(await page.locator('#canvas').innerText()));
    assert(await page.locator('#save').isDisabled());
    assert.equal(await page.locator('#download').getAttribute('aria-disabled'),'true');
    assert.match(await page.locator('#note').innerText(),/Tekrar dene/);
    await page.click('#zoom-in');
   }
   assert.deepEqual(errors,[],scenario); await page.close();
  }
  console.log('PASS: bundled SVG, transient retry, expiry, missing file and sign-in return URL');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
