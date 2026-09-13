const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function context() {
  const events = {}, nodes = {}, destinations = [], requests = [];
  const node = () => ({textContent: '', hidden: true, attrs: {},
    setAttribute(k,v) { this.attrs[k]=v; }, removeAttribute(k) { delete this.attrs[k]; },
    insertAdjacentElement() {}});
  const c = {URL, URLSearchParams, AbortController, setTimeout, clearTimeout,
    localStorage: {getItem() { throw Error('storage disabled'); }},
    location: {origin:'https://app.example', pathname:'/', search:'', hash:'',
      assign(u) {destinations.push(u);}, replace(u) {destinations.push(u);}},
    history: {replaceState(_,__,u) {c.cleaned=u;}},
    document: {getElementById(id) {return nodes[id] || null;}, createElement:node,
      addEventListener(k,fn) {events[k]=fn;}, body:{classList:{add(){}}}},
    window: {addEventListener(k,fn) {events[k]=fn;}},
    fetch:async (url,opts) => {requests.push([url,opts]);return {ok:true,json:async()=>({})};}
  };
  return {c,events,nodes,destinations,requests,node};
}

test('Google click starts directly, locks duplicates, and recovers on back navigation', async()=>{
  const h=context(); let resolve;
  h.c.fetch=async u=>u==='/api/account' ? {json:async()=>({})} : new Promise(r=>resolve=r);
  vm.runInNewContext(fs.readFileSync('web/nav-auth.js','utf8'),h.c);
  const link=h.node();link.href='https://app.example/account?next=%2Fconnect';
  const e={button:0,target:{closest:()=>link},preventDefault(){}};
  const first=h.events.click(e);
  await h.events.click(e);
  assert.equal(link.attrs['aria-disabled'],'true');
  resolve({ok:true,json:async()=>({url:'https://auth.example/authorize'})});
  await first;
  assert.deepEqual(h.destinations,['https://auth.example/authorize']);
  h.events.pageshow(); assert.equal(link.attrs['aria-disabled'],undefined);
});

test('network failure unlocks the login control for retry',async()=>{
  const h=context();h.c.fetch=async()=>{throw Error('offline');};
  vm.runInNewContext(fs.readFileSync('web/nav-auth.js','utf8'),h.c);
  const link=h.node();link.href='https://app.example/auth/google';
  await h.events.click({button:0,target:{closest:()=>link},preventDefault(){}});
  assert.equal(link.attrs['aria-disabled'],undefined);
  assert.deepEqual(h.destinations,[]);
});

const callback=fs.readFileSync('web/auth-callback.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
test('callback removes tokens before POST and goes directly to the preserved destination',async()=>{
  const h=context(); for(const id of ['retry','title','status'])h.nodes[id]=h.node();
  h.c.location.hash='#access_token=secret';h.c.location.search='?next=%2Fconnect';
  h.c.fetch=async(url,opts)=>{
    assert.ok(h.c.cleaned);assert.ok(!h.c.cleaned.includes('secret'));
    assert.equal(JSON.parse(opts.body).access_token,'secret');
    return {ok:true,json:async()=>({user:{id:'u'}})};
  };
  await vm.runInNewContext(callback,h.c);
  assert.deepEqual(h.destinations,['/connect']);
});

test('cancelled Google login shows a retry without creating a session',async()=>{
  const h=context();for(const id of ['retry','title','status'])h.nodes[id]=h.node();
  h.c.location.hash='#error=access_denied';
  await vm.runInNewContext(callback,h.c);
  assert.equal(h.requests.length,0);assert.equal(h.nodes.retry.hidden,false);
  assert.deepEqual(h.destinations,[]);
});
