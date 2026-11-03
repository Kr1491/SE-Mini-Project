'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/memberships.js'),'utf8');
function response(status,data={}){return {ok:status>=200&&status<300,status,json:async()=>data};}
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
function descendants(node){return node.children.flatMap(child=>[child,...descendants(child)]);}
class Element{
 constructor(){this.children=[];this.handlers={};this.dataset={};this.hidden=false;this.disabled=false;this.value='';this.textContent='';this.tag='';const c=new Set();this.classList={toggle:(key,on)=>on?c.add(key):c.delete(key),contains:key=>c.has(key)};}
 append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];}addEventListener(name,handler){this.handlers[name]=handler;}
 querySelectorAll(tag){return descendants(this).filter(node=>node.tag===tag);}
 closest(selector){return selector==='[data-review-request]'&&this.dataset.reviewRequest?this:null;}
}
function harness(custom=()=>undefined){
 const elements=new Map(),calls=[];const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
 const fetch=async(url,options={})=>{calls.push({url,options});const value=custom(url,options);if(value!==undefined)return value;return response(200,{requests:[],can_review:false,read_only:false});};
 const context={document:{getElementById:get,createElement:tag=>{const node=new Element();node.tag=tag;return node;}},fetch};
 vm.runInNewContext(source,context,{filename:'memberships.js'});
 return {get,calls,ui:context.StudyMemberships,
  load:(role='student',options={})=>context.StudyMemberships.load({user:{id:role==='student'?4:1,role},csrf_token:'active-csrf'},options),
  join:id=>{get('request-group-id').value=String(id);return get('request-join-form').handlers.submit({preventDefault(){}});},
  review:decision=>{const button=descendants(get('membership-requests')).find(node=>node.dataset.decision===decision);return get('membership-requests').handlers.click({target:button});}};
}

test('restricted join displays pending and does not claim membership or reload as joined',async()=>{
 let joined=false;
 const ui=harness((url,options)=>options.method==='POST'?response(202,{joined:false,message:'Waiting for approval.'}):undefined);
 await ui.load('student',{onJoined:()=>{joined=true;}});await ui.join(3);
 const post=ui.calls.find(call=>call.options.method==='POST');
 assert.equal(post.url,'/api/groups/3/join');assert.equal(post.options.headers['X-CSRF-Token'],'active-csrf');
 assert.equal(ui.get('membership-status').textContent,'Waiting for approval.');assert.equal(joined,false);
});

test('open join calls the dashboard refresh callback only after success',async()=>{
 let result;
 const ui=harness((url,options)=>options.method==='POST'?response(201,{joined:true,group:{id:1,name:'Open group'}}):undefined);
 await ui.load('student',{onJoined:value=>{result=value;}});await ui.join(1);
 assert.equal(result.group.id,1);assert.equal(ui.get('request-join-button').disabled,false);
});

test('manager can approve requests with CSRF and sees no stale requester after refresh',async()=>{
 let approved=false;
 const ui=harness((url,options)=>{
  if(options.method==='POST'){approved=true;return response(200,{status:'approved'});}
  return response(200,{can_review:true,read_only:false,requests:approved?[]:[{id:7,group_name:'Restricted class',student_name:'Requester',student_email:'request@example.test'}]});
 });
 await ui.load('instructor');assert.equal(ui.get('request-join-form').hidden,true);await ui.review('approve');
 const post=ui.calls.find(call=>call.options.method==='POST');assert.equal(post.url,'/api/membership-requests/7/review');
 assert.deepEqual(JSON.parse(post.options.body),{decision:'approve'});assert.equal(post.options.headers['X-CSRF-Token'],'active-csrf');
 assert.match(ui.get('membership-status').textContent,/approved/);
});

test('old account request cannot restore private membership data after switching roles',async()=>{
 const old=deferred();let loads=0;
 const ui=harness(()=>++loads===1?old.promise:response(200,{requests:[],can_review:false,read_only:false}));
 const pending=ui.load('instructor');await ui.load('student');
 old.resolve(response(200,{can_review:true,read_only:false,requests:[{id:1,group_name:'Old private data',student_name:'Old requester',student_email:'old@example.test'}]}));await pending;
 assert.equal(descendants(ui.get('membership-requests')).some(node=>node.textContent==='Old private data'),false);
 assert.equal(ui.get('request-join-form').hidden,false);
});

test('sample membership controls are read-only and never submit mutations',async()=>{
 const ui=harness(()=>response(200,{requests:[],can_review:false,read_only:true}));await ui.load();await ui.join(3);
 assert.equal(ui.get('membership-demo-notice').hidden,false);assert.equal(ui.get('request-join-button').disabled,true);
 assert.equal(ui.calls.some(call=>call.options.method==='POST'),false);
});

test('duplicate requests while saving are ignored and invalid group IDs never submit',async()=>{
 const pending=deferred();const ui=harness((url,options)=>options.method==='POST'?pending.promise:undefined);
 await ui.load();await ui.join('../3');assert.equal(ui.calls.some(call=>call.options.method==='POST'),false);
 const saving=ui.join(3);await ui.join(3);assert.equal(ui.calls.filter(call=>call.options.method==='POST').length,1);
 pending.resolve(response(202,{joined:false,message:'Pending'}));await saving;
 assert.equal(ui.get('request-join-button').disabled,false);
});

test('membership names and requester details remain literal text',async()=>{
 const malicious='<img src=x onerror=alert(1)>';
 const ui=harness(()=>response(200,{can_review:true,read_only:false,requests:[{id:1,group_name:malicious,student_name:malicious,student_email:'a@example.test'}]}));
 await ui.load('administrator');assert.ok(descendants(ui.get('membership-requests')).some(node=>node.textContent===malicious));
 assert.equal(descendants(ui.get('membership-requests')).some(node=>node.tag==='img'||node.tag==='script'),false);
});
