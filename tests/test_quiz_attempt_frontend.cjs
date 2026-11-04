'use strict';
const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/quiz-attempt.js'),'utf8');
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function descendants(node){return node.children.flatMap(child=>[child,...descendants(child)]);}
function attempt(id=7){return {attempt_id:id,quiz:{id:1,title:'A quiz',questions:[{id:10,question:'Question one',options:[{id:100,text:'First'},{id:101,text:'Second'}]},{id:20,question:'Question two',options:[{id:200,text:'Third'},{id:201,text:'Fourth'}]}]}};}
function receipt(extra={}){return {submitted:true,already_submitted:false,message:'Submission saved.',answers:[{question_id:10,option_id:100}],result:{score:1,max_score:2,answered_count:1,unanswered_count:1},...extra};}
class Element{
 constructor(tag='',id=''){this.tagName=tag;this.id=id;this.children=[];this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.checked=false;const values=new Set();this.classList={toggle:(key,on)=>on?values.add(key):values.delete(key),contains:key=>values.has(key)};}
 append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];}
 querySelectorAll(selector){const match=selector.match(/^input(?:\[name="([^"]+)"\])?(:checked)?$/);return match?descendants(this).filter(node=>node.tagName==='input'&&(!match[1]||node.name===match[1])&&(!match[2]||node.checked)):[];}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
function harness(custom=async()=>receipt(),data=attempt()){
 const elements=new Map(),created=[],calls=[],denied=[];
 const get=id=>{if(!elements.has(id))elements.set(id,new Element('',id));return elements.get(id);};
 get('quiz-attempt-form').append(get('attempt-questions'));
 const context={document:{getElementById:get,createElement:tag=>{const node=new Element(tag);created.push(node);return node;}}};
 vm.runInNewContext(source,context,{filename:'quiz-attempt.js'});
 const options={request:async(url,config)=>{calls.push({url,config});return custom(url,config);},onDenied:error=>denied.push(error.status)};
 context.StudyQuizAttempt.open(data,options);
 return {get,created,calls,denied,ui:context.StudyQuizAttempt,
  open:next=>context.StudyQuizAttempt.open(next,options),
  choose:(qid,oid)=>{for(const node of get('attempt-questions').querySelectorAll(`input[name="question-${qid}"]`))node.checked=node.value===String(oid);},
  submit:()=>get('quiz-attempt-form').onsubmit?.({preventDefault(){}}),confirm:()=>get('confirm-quiz-submit').onclick?.(),edit:()=>get('edit-quiz-answers').onclick?.(),close:()=>get('close-quiz-attempt').onclick?.()};
}

test('unanswered questions are warned about and no post happens before confirmation',()=>{
 const ui=harness();ui.choose(10,100);ui.submit();
 assert.equal(ui.calls.length,0);assert.equal(ui.get('attempt-confirmation').hidden,false);
 assert.match(ui.get('attempt-confirmation-text').textContent,/1 question is unanswered/);
 ui.edit();assert.equal(ui.get('attempt-confirmation').hidden,true);assert.equal(ui.get('submit-quiz-attempt').disabled,false);
});

test('confirmed submit posts selections to the existing attempt API and displays the server grade',async()=>{
 const ui=harness();ui.choose(10,100);ui.submit();await ui.confirm();
 assert.equal(ui.calls[0].url,'/api/quiz-attempts/7/submit');
 assert.deepEqual(JSON.parse(ui.calls[0].config.body),{answers:[{question_id:10,option_id:100}]});
 assert.equal(ui.get('attempt-score').textContent,'1 / 2');assert.match(ui.get('attempt-result-summary').textContent,/1 answered · 1 unanswered/);
 assert.equal(ui.get('attempt-result').hidden,false);assert.equal(ui.get('submit-quiz-attempt').disabled,true);
 assert.ok(ui.get('attempt-questions').querySelectorAll('input').every(input=>input.disabled));
});

test('all unanswered posts an empty list and displays a genuine zero score',async()=>{
 const ui=harness(async()=>receipt({answers:[],result:{score:0,max_score:2,answered_count:0,unanswered_count:2}}));
 ui.submit();assert.match(ui.get('attempt-confirmation-text').textContent,/2 questions are unanswered/);await ui.confirm();
 assert.deepEqual(JSON.parse(ui.calls[0].config.body).answers,[]);assert.equal(ui.get('attempt-score').textContent,'0 / 2');
});

test('double clicks and submit events while saving make one request',async()=>{
 const pending=deferred();const ui=harness(()=>pending.promise);ui.choose(10,100);ui.submit();
 const saving=ui.confirm();await ui.confirm();ui.submit();ui.close();
 assert.equal(ui.calls.length,1);assert.equal(ui.get('close-quiz-attempt').disabled,true);
 pending.resolve(receipt());await saving;assert.equal(ui.get('close-quiz-attempt').disabled,false);
});

test('a lost response retries the same confirmed payload and restores the saved selections',async()=>{
 let tries=0;const ui=harness(async()=>{if(++tries===1)throw Error('Offline');return receipt({already_submitted:true,message:'Original submission saved.'});});
 ui.choose(10,100);ui.submit();await ui.confirm();assert.equal(ui.get('submit-quiz-attempt').textContent,'Retry submission');
 ui.choose(10,101);await ui.submit();
 assert.equal(ui.calls[0].config.body,ui.calls[1].config.body);
 assert.equal(ui.get('attempt-questions').querySelector('input[name="question-10"]:checked').value,'100');
 assert.equal(ui.get('attempt-message').textContent,'Original submission saved.');
});

test('an old response cannot reveal a previous account result after reset',async()=>{
 const pending=deferred();const ui=harness(()=>pending.promise);ui.choose(10,100);ui.submit();const saving=ui.confirm();ui.ui.reset();
 pending.resolve(receipt());await saving;
 assert.equal(ui.get('attempt-score').textContent,'');assert.equal(ui.get('quiz-attempt-panel').hidden,true);
 assert.equal(ui.get('attempt-questions').children.length,0);
});

test('old response cannot replace a new attempt in the same account',async()=>{
 const pending=deferred();const ui=harness(()=>pending.promise);ui.submit();const saving=ui.confirm();
 ui.open({...attempt(8),quiz:{...attempt().quiz,title:'New attempt'}});pending.resolve(receipt());await saving;
 assert.equal(ui.get('attempt-quiz-title').textContent,'New attempt');assert.equal(ui.get('attempt-result').hidden,true);
});

test('authorization loss clears private questions before reporting denial',async()=>{
 const ui=harness(async()=>{const error=new Error('Access removed');error.status=403;throw error;});ui.submit();await ui.confirm();
 assert.deepEqual(ui.denied,[403]);assert.equal(ui.get('attempt-questions').children.length,0);assert.equal(ui.get('quiz-attempt-panel').hidden,true);
});

test('validation errors allow editing, while changed quiz data requires a new attempt',async()=>{
 for(const status of [400,409]){
  const ui=harness(async()=>{const error=new Error('Check this attempt');error.status=status;throw error;});ui.submit();await ui.confirm();
  assert.equal(ui.get('submit-quiz-attempt').disabled,status===409);
  assert.equal(ui.get('attempt-questions').querySelectorAll('input')[0].disabled,status===409);
  assert.match(ui.get('attempt-message').textContent,/Check this attempt/);
 }
});

test('closing removes selections and clears score before another attempt opens',async()=>{
 const ui=harness();ui.choose(10,100);ui.submit();await ui.confirm();ui.close();
 assert.equal(ui.get('group-quizzes').hidden,false);assert.equal(ui.get('attempt-questions').children.length,0);
 assert.equal(ui.get('attempt-score').textContent,'');ui.open(attempt(9));
 assert.equal(ui.get('submit-quiz-attempt').disabled,false);assert.equal(ui.get('attempt-result').hidden,true);
});

test('question and option text remain literal DOM text',()=>{
 const data=attempt();const text='<img src=x onerror=alert(1)>';data.quiz.title=text;data.quiz.questions[0].question=text;data.quiz.questions[0].options[0].text=text;
 const ui=harness(undefined,data);assert.equal(ui.get('attempt-quiz-title').textContent,text);
 assert.ok(ui.created.some(node=>node.textContent==='1. '+text));assert.equal(ui.created.some(node=>['img','script'].includes(node.tagName)),false);
});

test('earlier ungraded submission is labelled unavailable instead of zero',async()=>{
 const ui=harness(async()=>receipt({result:null,already_submitted:true}));ui.submit();await ui.confirm();
 assert.equal(ui.get('attempt-score').textContent,'Score unavailable');assert.equal(ui.get('submit-quiz-attempt').disabled,true);
});
