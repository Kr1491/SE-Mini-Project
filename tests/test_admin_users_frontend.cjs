'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/admin-users.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise,resolve}; }
function response(status,data={}) { return {ok:status>=200&&status<300,status,json:async()=>data}; }
const roles = ['student','instructor','administrator'].map(value=>({value,label:value,permissions:[value+' permissions']}));
function account(id=2,extra={}) { return {id,name:id===3?'Administrator':'Student account',email:`account${id}@example.test`,role:id===3?'administrator':'student',is_active:true,version:0,is_you:id===3,...extra}; }
function listing(users=[account(3),account()],extra={}) { return {users,total:users.length,roles,read_only:false,limit:20,offset:0,...extra}; }
class Element {
  constructor(tag='',id='') {
    this.tag=tag;this.id=id;this.children=[];this.dataset={};this.handlers={};this.attributes={};this.open=false;this.textContent='';this.value=id==='access-filter'?'all':'';this.disabled=false;this.hidden=['manage-content','demo-notice'].includes(id);
    const classes=new Set();this.classList={toggle:(key,value)=>value?classes.add(key):classes.delete(key),contains:key=>classes.has(key)};
  }
  append(...values) { this.children.push(...values); }
  replaceChildren(...values) { this.children=[...values]; }
  addEventListener(name,handler) { this.handlers[name]=handler; }
  setAttribute(name,value) { this.attributes[name]=value; }
  closest(selector) { return selector==='[data-save]'&&this.dataset.save?this:null; }
  showModal() { this.open=true; }
  close() { this.open=false;this.handlers.close?.(); }
}
function harness(custom=()=>undefined,sessionRole='administrator') {
  const elements=new Map(),created=[],calls=[],navigations=[];
  const get=id=>{if(!elements.has(id))elements.set(id,new Element('',id));return elements.get(id);};
  const fetch=async(url,options={})=>{
    calls.push({url,options});const result=custom(url,options);if(result!==undefined)return result;
    if(url==='/api/session')return response(200,{user:{id:3,name:'Admin viewer',role:sessionRole},csrf_token:'current-csrf'});
    if(url.startsWith('/api/admin/users?'))return response(200,listing());
    if(options.method==='POST')return response(200,{changed:true,message:'Account updated.'});
    throw Error('Unexpected route '+url);
  };
  vm.runInNewContext(source,{document:{getElementById:get,createElement:tag=>{const value=new Element(tag);created.push(value);return value;}},fetch,URLSearchParams,location:{replace:url=>navigations.push(url)}},{filename:'admin-users.js'});
  const row=id=>get('user-rows').children.find(row=>row.children[3]?.children[0]?.dataset.save===String(id));
  return {get,created,calls,navigations,row,
    edit:(id,role,active=true)=>{const value=row(id);value.children[1].children[0].value=role;value.children[2].children[0].value=active?'active':'inactive';get('user-rows').handlers.change();},
    review:id=>get('user-rows').handlers.click({target:row(id).children[3].children[0]}),
    confirm:()=>get('confirm-change').handlers.click(),cancel:()=>get('cancel-change').handlers.click(),
    refresh:()=>get('refresh-users').handlers.click(),
    search:(q,role='',access='all')=>{get('account-search').value=q;get('role-filter').value=role;get('access-filter').value=access;return get('account-filters').handlers.submit({preventDefault(){}});},
    next:()=>get('next-page').handlers.click()};
}

test('admin sees safe literal account data and own controls are protected',async()=>{
 const name='<img src=x onerror=alert(1)>';
 const ui=harness(url=>url.startsWith('/api/admin/users?')?response(200,listing([account(3),account(2,{name})])):undefined);
 await flush();assert.equal(ui.get('manage-content').hidden,false);
 assert.equal(ui.row(2).children[0].children[0].children[0].textContent,name);
 assert.equal(ui.row(3).children[1].children[0].disabled,true);
 assert.equal(ui.row(2).children[3].children[0].disabled,true);
 assert.equal(ui.created.some(node=>node.tag==='img'||node.tag==='script'),false);
});

test('editing requires review and explicit confirmation before posting',async()=>{
 const ui=harness();await flush();ui.edit(2,'instructor',false);ui.review(2);
 assert.equal(ui.get('confirm-dialog').open,true);
 assert.equal(ui.calls.some(call=>call.options.method==='POST'),false);
 await ui.confirm();const write=ui.calls.find(call=>call.options.method==='POST');
 assert.equal(write.url,'/api/admin/users/2');assert.equal(write.options.headers['X-CSRF-Token'],'current-csrf');
 assert.deepEqual(JSON.parse(write.options.body),{role:'instructor',is_active:false,version:0});
 assert.equal(ui.get('confirm-dialog').open,false);assert.equal(ui.get('admin-status').textContent,'Account updated.');
});

test('cancelling a proposed edit makes no write and keeps the edit reviewable',async()=>{
 const ui=harness();await flush();ui.edit(2,'instructor');ui.review(2);ui.cancel();
 assert.equal(ui.calls.some(call=>call.options.method==='POST'),false);
 assert.equal(ui.get('confirm-dialog').open,false);assert.equal(ui.row(2).children[3].children[0].disabled,false);
});

test('pending save blocks duplicate confirmation and filter changes',async()=>{
 const save=deferred();const ui=harness((url,options)=>options.method==='POST'?save.promise:undefined);
 await flush();ui.edit(2,'instructor');ui.review(2);const pending=ui.confirm();await ui.confirm();await ui.search('other');
 assert.equal(ui.calls.filter(call=>call.options.method==='POST').length,1);
 assert.equal(ui.get('apply-filters').disabled,true);
 save.resolve(response(200,{message:'Saved once.'}));await pending;
 assert.equal(ui.get('apply-filters').disabled,false);assert.equal(ui.get('admin-status').textContent,'Saved once.');
});

test('version conflict refreshes the list and keeps the conflict message',async()=>{
 let updated=false;
 const ui=harness((url,options)=>{
  if(options.method==='POST'){updated=true;return response(409,{error:'Account changed. Review again.'});}
  if(url.startsWith('/api/admin/users?'))return response(200,listing([account(3),account(2,{role:updated?'administrator':'student',version:updated?1:0})]));
 });
 await flush();ui.edit(2,'instructor');ui.review(2);await ui.confirm();
 assert.equal(ui.row(2).children[1].children[0].value,'administrator');
 assert.equal(ui.get('admin-status').textContent,'Account changed. Review again.');
 assert.equal(ui.row(2).children[3].children[0].disabled,true);
});

test('role/access/search filters reset paging and preserve literal search text',async()=>{
 const ui=harness();await flush();await ui.search("O'Neil & test",'student','inactive');
 const params=new URLSearchParams(ui.calls.at(-1).url.split('?')[1]);
 assert.equal(params.get('q'),"O'Neil & test");assert.equal(params.get('role'),'student');assert.equal(params.get('access'),'inactive');assert.equal(params.get('offset'),'0');
});

test('slow old searches cannot replace the newest results or clear them on an old denial',async()=>{
 const old=deferred();
 const ui=harness(url=>url.includes('q=old')?old.promise:url.includes('q=new')?response(200,listing([account(22,{name:'New result'})])):undefined);
 await flush();const pending=ui.search('old');await ui.search('new');old.resolve(response(403,{error:'Old denial'}));await pending;
 assert.equal(ui.get('manage-content').hidden,false);assert.ok(ui.row(22));assert.equal(ui.get('admin-status').textContent,'');
});

test('demo accounts remain read-only even when a fake edit event is attempted',async()=>{
 const ui=harness(url=>url.startsWith('/api/admin/users?')?response(200,listing(undefined,{read_only:true})):undefined);
 await flush();assert.equal(ui.get('demo-notice').hidden,false);
 assert.equal(ui.row(2).children[1].children[0].disabled,true);
 ui.edit(2,'administrator');ui.review(2);await ui.confirm();
 assert.equal(ui.calls.some(call=>call.options.method==='POST'),false);
});

test('a nonadministrator session never requests or shows the user list',async()=>{
 const ui=harness(()=>undefined,'student');await flush();
 assert.equal(ui.calls.some(call=>call.url.startsWith('/api/admin/users')),false);
 assert.equal(ui.get('manage-content').hidden,true);assert.match(ui.get('admin-status').textContent,/Administrator/);
});

test('expired session on refresh clears private rows/profile and opens login',async()=>{
 let expired=false;const ui=harness(url=>expired&&url.startsWith('/api/admin/users?')?response(401,{error:'Expired'}):undefined);
 await flush();expired=true;await ui.refresh();
 assert.equal(ui.get('user-rows').children.length,0);assert.equal(ui.get('admin-profile').textContent,'');
 assert.equal(ui.get('manage-content').hidden,true);assert.deepEqual(ui.navigations,['/login']);
});

test('authorization failure during save closes dialog and clears private content',async()=>{
 const ui=harness((url,options)=>options.method==='POST'?response(403,{error:'No longer an administrator'}):undefined);
 await flush();ui.edit(2,'instructor');ui.review(2);await ui.confirm();
 assert.equal(ui.get('confirm-dialog').open,false);assert.equal(ui.get('user-rows').children.length,0);
 assert.equal(ui.get('manage-content').hidden,true);assert.match(ui.get('admin-status').textContent,/Administrator/);
});

test('paging uses server page length and returns to the first page after filter change',async()=>{
 const ui=harness(url=>url.startsWith('/api/admin/users?')?response(200,listing([account(2)],{limit:1,total:3,offset:Number(new URLSearchParams(url.split('?')[1]).get('offset'))})):undefined);
 await flush();await ui.next();assert.equal(new URLSearchParams(ui.calls.at(-1).url.split('?')[1]).get('offset'),'1');
 await ui.search('student');assert.equal(new URLSearchParams(ui.calls.at(-1).url.split('?')[1]).get('offset'),'0');
});
