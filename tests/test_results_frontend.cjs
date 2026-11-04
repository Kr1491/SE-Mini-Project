'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/results.js'), 'utf8');
class Element {
  constructor(tag) { this.tagName=tag; this.children=[]; this.textContent=''; this.hidden=false; this.classList={remove(){},add(){}}; }
  append(...items) {this.children.push(...items);}
  replaceChildren(...items) {this.children=items;}
}
function ui() {
  const items = new Map();
  const get = id => {if (!items.has(id)) items.set(id,new Element('div'));return items.get(id);};
  const context = {document:{getElementById:get,createElement:tag=>new Element(tag)}};
  vm.runInNewContext(source, context);
  return {get,...context.StudyResults};
}
const session = role => ({user:{id:2,role}});
const result = {quiz_title:'Quiz',student_name:'Student',score:1,total_questions:2,percentage:50,submitted_at:'2026-11-04T10:00:00Z'};
const contents = node => [node.textContent,...node.children.map(contents)].join(' ');
const groups = [{id:1,name:'Owned',can_manage:true},{id:2,name:'Member',can_manage:false},{id:3,name:'Other owned',can_manage:true}];
function pending() {let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
test('Student sees own results and no staff names or group selector',async()=>{
  const app=ui();let path;
  await app.load(session('student'),{request:async p=>{path=p;return {results:[result]};}});
  assert.equal(path,'/api/results/me');assert.equal(app.get('performance-group-control').hidden,true);
  assert.match(contents(app.get('results-list')),/1 \/ 2/);assert.doesNotMatch(contents(app.get('results-list')),/Student/);
});
test('legacy submissions display unavailable grades without inventing zero',async()=>{
  const app=ui();await app.load(session('student'),{request:async()=>({results:[{...result,score:null,total_questions:null,percentage:null}]})});
  assert.match(contents(app.get('results-list')),/Score unavailable/);assert.doesNotMatch(contents(app.get('results-list')),/0 \/|null%/);
});
test('staff selector includes only manageable groups and uses scoped endpoint',async()=>{
  const app=ui();const paths=[];await app.load(session('instructor'),{groups,request:async p=>{paths.push(p);return {results:[result]};}});
  assert.equal(app.get('performance-group').children.length,3);assert.equal(paths.length,0);
  app.get('performance-group').value='1';await app.get('performance-group').onchange();
  assert.equal(paths[0],'/api/groups/1/results');assert.match(contents(app.get('results-list')),/Student/);
  app.get('performance-group').value='2';await app.get('performance-group').onchange();assert.equal(paths.length,1);
});
test('slower previous group response cannot replace latest selection',async()=>{
  const app=ui();const first=pending();
  await app.load(session('instructor'),{groups,request:async p=>p.includes('/1/')?first.promise:{results:[{...result,quiz_title:'Latest'}]}});
  app.get('performance-group').value='1';const earlier=app.get('performance-group').onchange();
  app.get('performance-group').value='3';await app.get('performance-group').onchange();
  first.resolve({results:[{...result,quiz_title:'Earlier'}]});await earlier;
  assert.match(contents(app.get('results-list')),/Latest/);assert.doesNotMatch(contents(app.get('results-list')),/Earlier/);
});
test('reset removes private results and ignores late account responses',async()=>{
  const app=ui();const response=pending();const work=app.load(session('student'),{request:()=>response.promise});
  app.reset();response.resolve({results:[result]});await work;
  assert.equal(app.get('results-panel').hidden,true);assert.equal(app.get('results-list').children.length,0);
});
test('expired or forbidden sessions clear results and notify parent',async()=>{
  for(const status of [401,403]){const app=ui();let denied;
    await app.load(session('student'),{request:async()=>{throw Object.assign(new Error('Denied'),{status});},onDenied:e=>denied=e.status});
    assert.equal(denied,status);assert.equal(app.get('results-panel').hidden,true);assert.equal(app.get('results-list').children.length,0);
  }
});
test('titles and student names are rendered as literal text',async()=>{
  const app=ui();await app.load(session('student'),{request:async()=>({results:[{...result,quiz_title:'<img src=x onerror=alert(1)>'}]})});
  const title=app.get('results-list').children[0].children[0];assert.equal(title.textContent,'<img src=x onerror=alert(1)>');assert.equal(title.children.length,0);
});
