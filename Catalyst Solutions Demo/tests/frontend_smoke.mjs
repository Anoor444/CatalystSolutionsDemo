// Dependency-free browser smoke test. Requires Python/Flask and Chrome or Edge.
import {spawn} from 'node:child_process';
import {mkdtempSync, existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const root=resolve(fileURLToPath(new URL('..',import.meta.url)));
const browserPath=process.env.BROWSER_PATH || ['C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
assert(browserPath,'Set BROWSER_PATH to a Chrome/Edge executable.');
const temp=mkdtempSync(join(tmpdir(),'buffbison-qa-'));
const server=spawn('python',['-c',"from app import app; app.run(port=5187, debug=False)"],{cwd:root,env:{...process.env,APP_INSTANCE_PATH:join(temp,'instance'),DB_BACKEND:'sqlite'},windowsHide:true,stdio:'ignore'});
const browser=spawn(browserPath,['--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=9287',`--user-data-dir=${join(temp,'browser')}`],{windowsHide:true,stdio:'ignore'});
let socket;const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function ready(url){for(let n=0;n<100;n++){try{const r=await fetch(url);if(r.ok)return r;}catch{}await sleep(100);}throw Error('Not ready: '+url);}
try {
  await ready('http://127.0.0.1:5187/login');await ready('http://127.0.0.1:9287/json/version');
  const target=await (await fetch('http://127.0.0.1:9287/json/new?about:blank',{method:'PUT'})).json();
  socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>socket.onopen=r);
  let seq=0;const pending=new Map(),errors=[];
  socket.onmessage=ev=>{const m=JSON.parse(ev.data);if(m.id){const [ok,fail]=pending.get(m.id)||[];pending.delete(m.id);m.error?fail?.(m.error):ok?.(m.result);}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.exception?.description||m.params.exceptionDetails.text);};
  const send=(method,params={})=>new Promise((ok,fail)=>{const id=++seq;pending.set(id,[ok,fail]);socket.send(JSON.stringify({id,method,params}));});
  await send('Runtime.enable');await send('Page.enable');
  await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:temp});
  async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
  async function go(path){await send('Page.navigate',{url:'http://127.0.0.1:5187'+path});await sleep(150);for(let i=0;i<80;i++){try{if(await evaluate("document.readyState==='complete'"))return;}catch{}await sleep(50);}throw Error('Navigation timed out');}
  async function login(email,password){await go('/login');await evaluate(`document.querySelector('[name=email]').value=${JSON.stringify(email)};document.querySelector('[name=password]').value=${JSON.stringify(password)};document.querySelector('form').requestSubmit()`);await sleep(350);assert.equal(await evaluate('location.pathname'),'/dashboard');}
  async function logout(){await evaluate("document.querySelector('form[action=\"/logout\"]').requestSubmit()");await sleep(250);}
  await login('demo@buffbison.com','Buffbison123');
  for(const path of ['/dashboard','/projects','/project/2','/invoices','/estimates','/job-costs','/schedule','/documents','/photos','/new-project']){await go(path);assert.equal(await evaluate('!!window.Demo'),true,path);}
  await go('/projects');assert.equal(await evaluate("document.querySelectorAll('.project-row').length"),12);
  await evaluate("document.querySelector('#project-search').value='Riverstone';document.querySelector('#project-search').dispatchEvent(new Event('input'))");
  assert.equal(await evaluate("[...document.querySelectorAll('.project-row')].filter(r=>!r.hidden).length"),1);
  await go('/project/5');assert(await evaluate("document.querySelector('main').textContent.includes('$14,700.00')"));
  await go('/project/2');assert.equal(await evaluate("document.querySelector('h1').textContent"),'Sugar Land Roof Replacement');
  await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Edit Project').click();document.querySelector('dialog [name=description]').value='Edited in browser QA';document.querySelector('dialog form').requestSubmit()");await sleep(250);
  assert(await evaluate("document.querySelector('main').textContent.includes('Edited in browser QA')"));
  await go('/new-project');await evaluate(`const f=document.querySelector('form.form-page');for(const [k,v] of Object.entries({project_name:'QA New Project',project_type:'Other',client_name:'QA Client',address:'123 Test Lane',manager:'Daniel Carter',budget:'1200',end_date:'2027-01-01'}))f.elements[k].value=v;f.requestSubmit()`);await sleep(250);assert.equal(await evaluate('location.pathname'),'/project/13');
  await evaluate("[...document.querySelectorAll('[role=tab]')].find(b=>b.textContent==='Subcontractors').click();[...document.querySelectorAll('button')].find(b=>b.textContent==='Assign Subcontractor').click();document.querySelector('dialog [name=trade]').value='Finish carpentry';document.querySelector('dialog form').requestSubmit()");await sleep(100);assert(await evaluate("Demo.projects().find(p=>p.id===13).subcontractors.some(s=>s.email==='demo.subcontractor@buffbison.com')"));
  for(const path of ['/estimates','/invoices','/job-costs','/schedule']) { await go(path); assert.equal(await evaluate("!!document.querySelector('.demo-banner')"),false, 'Original employee screen: '+path); }
  await go('/project/1');await evaluate("[...document.querySelectorAll('[role=tab]')].find(b=>b.textContent==='Invoices').click();[...document.querySelectorAll('button')].find(b=>b.textContent==='Create Invoice').click();const f=document.querySelector('dialog form');f.elements.project.value='1';f.elements.number.value='QA-100';f.querySelector('[name=description]').value='QA labor';f.querySelector('[name=qty]').value='2';f.querySelector('[name=rate]').value='125';f.requestSubmit()");await sleep(100);
  assert.equal(await evaluate("Demo.invoices().find(i=>i.number==='QA-100').lines[0].rate"),125);
  await go('/project/1');await evaluate("[...document.querySelectorAll('[role=tab]')].find(b=>b.textContent==='Invoices').click();[...document.querySelectorAll('[data-invoice]')].at(-1).click()");assert(await evaluate("document.querySelector('dialog').textContent.includes('$250.00')"));
  await evaluate("window.qaOriginalObjectURL=URL.createObjectURL;URL.createObjectURL=blob=>{window.qaPdf=blob;return window.qaOriginalObjectURL(blob)};[...document.querySelector('dialog').querySelectorAll('button')].find(b=>b.textContent==='Download PDF').click();[...document.querySelector('dialog').querySelectorAll('button')].find(b=>b.textContent==='Mark Paid').click()");
  assert.equal(await evaluate("Demo.invoices().find(i=>i.number==='QA-100').status"),'Paid');
  const pdf=await evaluate('window.qaPdf.text()');assert(pdf.startsWith('%PDF-1.4'));assert(pdf.includes('TOTAL: $250.00'));
  await go('/project/1');await evaluate("[...document.querySelectorAll('[role=tab]')].find(b=>b.textContent==='Documents').click();[...document.querySelectorAll('button')].find(b=>b.textContent==='Attach Receipt / Document').click();const f=document.querySelector('dialog form');f.elements.title.value='QA Receipt';const dt=new DataTransfer();dt.items.add(new File(['receipt'],'receipt.txt',{type:'text/plain'}));f.elements.file.files=dt.files;f.requestSubmit()");await sleep(100);assert(await evaluate("document.querySelector('[data-files]').textContent.includes('QA Receipt')"));
  await go('/documents');assert(await evaluate("document.querySelector('[data-files]').textContent.includes('QA Receipt')"));
  await go('/dashboard');await evaluate("const input=document.querySelector('input[type=search]');input.value='QA-100';input.dispatchEvent(new Event('input'))");assert(await evaluate("document.querySelector('.search-results').textContent.includes('QA-100')"));
  const invoiceHref=await evaluate("document.querySelector('.search-results a').getAttribute('href')");assert(invoiceHref.startsWith('/project/1?invoice='));await go(invoiceHref);assert(await evaluate("document.querySelector('dialog').textContent.includes('QA-100')"));
  await logout();await login('demo.subcontractor@buffbison.com','SubcontractorDemo123!');await go('/subcontractor/invoices');
  await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Submit Invoice').click();const f=document.querySelector('dialog form');f.elements.project.value='2';f.elements.number.value='QA-SC';f.querySelector('[name=description]').value='Roof labor';f.querySelector('[name=rate]').value='700';f.requestSubmit()");await sleep(100);assert(await evaluate("document.querySelector('[data-invoice-list]').textContent.includes('QA-SC')"));
  await go('/projects');assert(await evaluate("document.querySelector('main').textContent.includes('QA New Project')"));const assignedHref=await evaluate("[...document.querySelectorAll('tbody a')].find(a=>a.closest('tr').textContent.includes('QA New Project')).getAttribute('href')");await go(assignedHref);assert.equal(await evaluate("document.querySelector('h1').textContent"),'QA New Project');assert.equal(await evaluate("document.querySelector('main').textContent.includes('Project unavailable')"),false);
  await go('/photos/upload');assert.equal(await evaluate("document.querySelector('[name=project_name]').tagName"),'SELECT');assert.equal(await evaluate("document.querySelector('[name=project_name]').options.length"),5);
  await evaluate("const f=document.querySelector('form.form-page');f.elements.project_name.selectedIndex=1;f.elements.title.value='QA Photo';const dt=new DataTransfer();dt.items.add(new File([Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9x8AAAAASUVORK5CYII='),c=>c.charCodeAt(0))],'photo.png',{type:'image/png'}));f.querySelector('input[type=file]').files=dt.files;f.requestSubmit()");await sleep(250);assert.equal(await evaluate('location.pathname'),'/photos');assert(await evaluate("document.querySelector('[data-files]').textContent.includes('QA Photo')"));
  await logout();await login('demo.client@buffbison.com','ClientDemo123!');await go('/client/estimates');assert(await evaluate("document.querySelector('main').textContent.includes('Unit cost')"));await go('/client/invoices');assert(await evaluate("document.querySelector('main').textContent.includes('QA-100')"));assert.equal(await evaluate("[...document.querySelectorAll('button')].some(b=>b.textContent==='Create Invoice')"),false);await go('/project/1');assert.equal(await evaluate("[...document.querySelectorAll('button')].some(b=>b.textContent==='Edit Project')"),false);
  assert.deepEqual(errors,[],'Browser runtime errors');
  console.log('PASS: employee, client, and subcontractor workflows; restored employee screens, project creation/editing, project invoice totals/status/PDF, attachments, filters, search, and persistence.');
} finally {socket?.close();browser.kill();server.kill();}
