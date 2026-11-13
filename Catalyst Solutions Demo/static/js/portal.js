/* Frontend workflows shared by the three demo portals. */
(() => {
  'use strict';
  const D = window.Demo, E = D.esc, M = D.money;
  const role = window.portalContext.role, path = location.pathname;
  if (path === '/settings' || path === '/settings/change-password') return;
  // Preserve the original employee screens and their existing demo behavior.
  if (role === 'employee' && ['/estimates', '/invoices', '/job-costs', '/schedule'].includes(path)) return;
  const main = document.querySelector('main.content');
  if (!main) return;
  const banner = document.createElement('p'); banner.className = 'demo-banner';
  banner.textContent = 'Frontend demo: changes and attachments are saved in this browser. Portal assignments are sample data.';
  main.prepend(banner);
  const button = (text, fn, parent, cls='btn-outline') => { const b=document.createElement('button'); b.type='button'; b.className=cls; b.textContent=text; b.onclick=fn; parent.append(b); return b; };
  function dialog(title, html) {
    const el = document.createElement('dialog'); el.className='portal-dialog';
    el.setAttribute('aria-label',title); el.innerHTML=`<h2>${E(title)}</h2>${html}<div class="portal-actions" data-close></div>`;
    button('Close',()=>el.close(),el.querySelector('[data-close]'));
    el.addEventListener('close',()=>el.remove()); document.body.append(el); el.showModal(); return el;
  }
  function field(label,name,value='',type='text',required=true) { return `<label>${E(label)}<input name="${name}" type="${type}" value="${E(value)}" ${required?'required':''}></label>`; }
  function options(selected) { return D.visibleProjects().map(p=>`<option value="${p.id}" ${p.id===Number(selected)?'selected':''}>${E(p.name)}</option>`).join(''); }
  function table(head,rows) { return `<div class="table-wrap"><table><thead><tr>${head.map(h=>`<th>${E(h)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.join(''):`<tr><td colspan="${head.length}">No records yet.</td></tr>`}</tbody></table></div>`; }
  function error(el,err) { el.querySelector('[data-error]').textContent=err.message || String(err); }
  function projectLink(p) { return role === 'subcontractor' ? `/projects?project=${p.id}` : `/project/${p.id}`; }
  function invoiceVisible(i) { return D.visibleProjects().some(p=>p.id===i.project_id) && (role==='employee' || i.kind===(role==='client'?'client':'subcontractor')); }
  function invoiceRows(projectId) {
    return D.invoices().filter(i=>invoiceVisible(i)&&(!projectId||i.project_id===projectId));
  }
  const invoiceTotal = i => i.lines.reduce((s,l)=>s+l.quantity*l.rate,0);
  function invoiceDetail(i) {
    const p=D.projects().find(p=>p.id===i.project_id);
    const el=dialog(`Invoice #${i.number}`,`<p>${E(p?.name)} · ${E(p?.client)}</p><p>Issued ${E(i.date)} · Due ${E(i.due)} · ${E(i.status)}</p>${table(['Description','Quantity','Rate','Total'],i.lines.map(l=>`<tr><td>${E(l.description)}</td><td>${l.quantity}</td><td>${M(l.rate)}</td><td>${M(l.quantity*l.rate)}</td></tr>`))}<h3>Total ${M(invoiceTotal(i))}</h3><div data-invoice-actions class="portal-actions"></div>`);
    const actions=el.querySelector('[data-invoice-actions]'); button('Download PDF',()=>D.pdf(i),actions);
    if(i.attachment) { const a=document.createElement('a'); a.textContent=i.attachment.name; a.href=i.attachment.data; a.download=i.attachment.name; a.className='btn-outline'; actions.append(a); }
    if(role==='employee') button(i.status==='Paid'?'Mark Unpaid':'Mark Paid',()=>{
      const all=D.invoices(); all.find(x=>x.id===i.id).status=i.status==='Paid'?'Unpaid':'Paid';
      try { D.write('invoices',all); el.close(); renderInvoices(); } catch(err){ alert(err.message); }
    },actions);
  }
  function invoiceForm(projectId) {
    const sub=role==='subcontractor';
    const el=dialog(sub?'Submit Invoice':'Create Invoice',`<form data-invoice-form><label>Project<select name="project" required><option value="">Select project</option>${options(projectId)}</select></label>${field('Invoice number','number',`${sub?'SC-':''}${Date.now().toString().slice(-8)}`)}${field('Invoice date','date',D.today(),'date')}${field('Due date','due',D.today(),'date')}${sub?'':'<label>Invoice for<select name="kind"><option value="client">Client</option><option value="subcontractor">Subcontractor</option></select></label>'}<div class="table-wrap"><table><thead><tr><th>Description</th><th>Quantity</th><th>Rate ($)</th><th></th></tr></thead><tbody data-lines></tbody></table></div><div class="portal-actions" data-line-actions></div><p data-total aria-live="polite"></p><label>Attach invoice (optional, PDF/image, up to 2 MB)<input type="file" name="attachment" accept=".pdf,.png,.jpg,.jpeg,.webp"></label><p class="portal-error" data-error role="alert"></p><button class="btn" type="submit">${sub?'Submit Invoice':'Create Invoice'}</button></form>`);
    const form=el.querySelector('form'), body=el.querySelector('[data-lines]');
    function total(){el.querySelector('[data-total]').textContent='Total: '+M([...body.rows].reduce((s,r)=>s+Number(r.querySelector('[name=qty]').value)*Number(r.querySelector('[name=rate]').value),0));}
    function add(){ const tr=body.insertRow(); tr.innerHTML='<td><input name="description" aria-label="Description" required maxlength="70"></td><td><input name="qty" aria-label="Quantity" type="number" min="0.01" step="0.01" value="1" required></td><td><input name="rate" aria-label="Rate" type="number" min="0" step="0.01" value="0" required></td><td></td>'; button('Remove',()=>{tr.remove();total();},tr.lastElementChild); }
    add(); button('Add line item',add,el.querySelector('[data-line-actions]')); form.oninput=total; total();
    form.onsubmit=async ev=>{ ev.preventDefault(); try {
      if(!body.rows.length) throw Error('Add at least one line item.');
      if(form.due.value<form.date.value) throw Error('Due date cannot precede invoice date.');
      const all=D.invoices(), number=form.number.value.trim();
      if(!number) throw Error('Enter an invoice number.');
      if(all.some(i=>i.number.toLowerCase()===number.toLowerCase())) throw Error('That invoice number already exists.');
      const lines=[...body.rows].map(r=>({description:r.querySelector('[name=description]').value.trim(),quantity:Number(r.querySelector('[name=qty]').value),rate:Number(r.querySelector('[name=rate]').value)}));
      if(lines.some(l=>!l.description||!Number.isFinite(l.quantity*l.rate)||l.quantity<=0||l.rate<0)) throw Error('Enter valid descriptions, quantities, and rates.');
      const attachment=form.attachment.files[0]?await readFile(form.attachment.files[0],false):null;
      all.push({id:Date.now(),number,project_id:Number(form.project.value),date:form.date.value,due:form.due.value,kind:sub?'subcontractor':form.kind.value,status:sub?'Pending Approval':'Unpaid',lines,attachment});
      D.write('invoices',all); el.close(); renderInvoices();
    }catch(err){error(el,err);} };
  }
  function renderInvoices() {
    const target=document.querySelector('[data-invoice-list]'); if(!target) return;
    const projectId=Number(target.dataset.project)||null, list=invoiceRows(projectId);
    target.innerHTML=table(['Invoice','Project','Due','Amount','Status','Actions'],list.map(i=>`<tr><td>#${E(i.number)}</td><td>${E(D.projects().find(p=>p.id===i.project_id)?.name)}</td><td>${E(i.due)}</td><td>${M(invoiceTotal(i))}</td><td>${E(i.status)}</td><td><button type="button" class="btn-outline" data-invoice="${i.id}">View</button></td></tr>`));
    target.querySelectorAll('[data-invoice]').forEach(b=>b.onclick=()=>invoiceDetail(list.find(i=>i.id===Number(b.dataset.invoice))));
  }
  function invoicePage() {
    main.innerHTML=''; main.append(banner); const card=document.createElement('section'); card.className='card';
    card.innerHTML=`<h2>${role==='subcontractor'?'Submitted Invoices':role==='client'?'Your Invoices':'Project Invoices'}</h2><div class="portal-actions" data-actions></div><div data-invoice-list></div>`; main.append(card);
    if(role!=='client') button(role==='subcontractor'?'Submit Invoice':'Create Invoice',()=>invoiceForm(),card.querySelector('[data-actions]'),'btn');
    renderInvoices();
    const requested=new URLSearchParams(location.search).get('invoice');
    const i=invoiceRows().find(i=>String(i.id)===requested); if(i) invoiceDetail(i);
  }
  function editProject(project) {
    const p=project||{};
    const el=dialog('Edit Project',`<form>${field('Project name','name',p.name)}${field('Client','client',p.client)}${field('Project manager','manager',p.manager)}${field('Address','address',p.address||'','text',false)}<label>Description<textarea name="description">${E(p.description||'')}</textarea></label>${field('Budget ($)','budget',p.budget,'number')}${field('Start date','start',p.start||'','date',false)}${field('Due date','due',p.due||'','date')}${field('Progress (%)','progress',p.progress||0,'number')}<label>Status<select name="status">${['Planning','In Progress','On Hold','Completed'].map(s=>`<option ${s===p.status?'selected':''}>${s}</option>`).join('')}</select></label><p data-error class="portal-error" role="alert"></p><button class="btn" type="submit">Save Project</button></form>`);
    const f=el.querySelector('form'); f.budget.min=0; f.budget.step='.01'; f.progress.min=0; f.progress.max=100;
    f.onsubmit=ev=>{ev.preventDefault();try{if(f.start.value&&f.due.value<f.start.value)throw Error('Due date cannot precede start date.'); const next={...p}; for(const key of ['name','client','manager','address','description','start','due','status'])next[key]=f.elements[key].value.trim();next.budget=Number(f.budget.value);next.progress=Number(f.progress.value);D.saveProject(next);location.reload();}catch(err){error(el,err);}};
  }
  function projectList() {
    const body=document.querySelector('#projects-table tbody'); if(!body)return;
    body.innerHTML=D.projects().map(p=>`<tr class="project-row" data-status="${E(p.status)}"><td>${E(p.name)}</td><td>${E(p.client)}</td><td>${E(p.manager)}</td><td>${E(p.status)}</td><td>${M(p.budget)}</td><td>${M(actual(p))}</td><td>${Number(p.progress||0)}%</td><td>${E(p.due)}</td><td><a href="${projectLink(p)}" class="btn-outline">View</a></td></tr>`).join('')+'<tr id="no-results" hidden><td colspan="9">No projects match your search.</td></tr>';
    const filter=()=>{let count=0;body.querySelectorAll('.project-row').forEach(r=>{r.hidden=!(r.cells[0].textContent+' '+r.cells[1].textContent).toLowerCase().includes(document.querySelector('#project-search').value.toLowerCase()) || (document.querySelector('#status-filter').value!=='All'&&r.dataset.status!==document.querySelector('#status-filter').value);if(!r.hidden)count++;});document.querySelector('#no-results').hidden=count>0;};
    document.querySelector('#project-search').oninput=filter;document.querySelector('#status-filter').onchange=filter;
    const cards=main.querySelectorAll('.summary-value'), all=D.projects(); [all.length,all.filter(p=>p.status==='In Progress').length,all.filter(p=>p.status==='Planning').length,all.filter(p=>p.status==='Completed').length].forEach((v,i)=>{if(cards[i])cards[i].textContent=v;});
  }
  function actual(p){return D.actualCost(p);}
  function projectDetails() {
    const query=new URLSearchParams(location.search);
    const id=Number(query.get('project') || path.split('/').pop()), p=D.visibleProjects().find(p=>p.id===id);
    if(!p){main.innerHTML='<section class="card"><h2>Project unavailable</h2><a href="/projects">Back to projects</a></section>';return;}
    document.querySelector('h1').textContent=p.name;document.title=p.name+' | Buff Bison';
    const heading=document.querySelector('.header .welcome');if(heading)heading.textContent=p.client+' · '+p.status;
    const oldEdit=document.querySelector('.header-right a.btn');if(oldEdit)oldEdit.remove();
    main.innerHTML='';main.append(banner);
    const overview=document.createElement('section');overview.className='card';overview.innerHTML=`<h2>${E(p.name)}</h2><p>${E(p.description||'Project details')}</p><p>Client: ${E(p.client)} · Manager: ${E(p.manager)}</p><p>${E(p.address||'Address not entered')}</p><p>Status: ${E(p.status)} · Progress: ${Number(p.progress||0)}%</p><p>Start: ${E(p.start||'Not set')} · Due: ${E(p.due||'Not set')}</p>${role==='employee'?`<p>Estimated: ${M(p.budget)} · Actual: ${M(actual(p))} · Remaining: ${M(p.budget-actual(p))}</p>`:''}<div class="portal-actions" data-actions></div>`;main.append(overview);
    if(role==='employee')button('Edit Project',()=>editProject(p),overview.querySelector('[data-actions]'),'btn');
    const tabs=document.createElement('div');tabs.className='portal-actions';tabs.setAttribute('role','tablist');main.append(tabs);
    const content=document.createElement('section');content.className='card';content.setAttribute('role','tabpanel');main.append(content);
    const names=role==='employee'?['Costs','Invoices','Documents','Photos','Schedule','Subcontractors','Estimate']:role==='client'?['Estimate','Invoices','Schedule']:['Photos','Invoices','Schedule'];
    function show(name){tabs.querySelectorAll('button').forEach(b=>{b.setAttribute('aria-selected',String(b.textContent===name));b.className=b.textContent===name?'btn':'btn-outline';});content.innerHTML=`<h2>${E(name)}</h2>`;
      if(name==='Invoices'){content.innerHTML+='<div class="portal-actions" data-actions></div><div data-invoice-list data-project="'+p.id+'"></div>';if(role!=='client')button(role==='employee'?'Create Invoice':'Submit Invoice',()=>invoiceForm(p.id),content.querySelector('[data-actions]'));renderInvoices();}
      if(name==='Costs'){const c=D.read('costs',{expenses:[]}); content.innerHTML+=`<p>Estimated ${M(p.budget)} · Actual ${M(actual(p))}</p>`+table(['Description','Category','Date','Actual'],c.expenses.filter(e=>e.project_id===p.id).map(e=>`<tr><td>${E(e.description)}</td><td>${E(e.category)}</td><td>${E(e.expense_date)}</td><td>${M(e.amount)}</td></tr>`))+`<a class="btn-outline" href="/job-costs?project=${p.id}">Manage costs</a>`;}
      if(name==='Documents'||name==='Photos'){const photo=name==='Photos';content.innerHTML+='<div class="portal-actions" data-actions></div><div data-files></div>';button(photo?'Upload Photo':'Attach Receipt / Document',()=>attachmentForm(p.id,photo,()=>show(name)),content.querySelector('[data-actions]'));renderFiles(content.querySelector('[data-files]'),p.id,photo);}
      if(name==='Schedule'){const tasks=D.read('tasks',[]).filter(t=>t.project_id===p.id);content.innerHTML+=table(['Task','Assigned to','Due','Status'],tasks.map(t=>`<tr><td>${E(t.name)}</td><td>${E(t.assigned_to)}</td><td>${E(t.due_date)}</td><td>${E(t.status)}</td></tr>`));if(role==='employee')content.innerHTML+=`<a class="btn-outline" href="/schedule?project=${p.id}">Manage tasks</a>`;}
      if(name==='Subcontractors')renderSubcontractors(content,p,()=>show(name));
      if(name==='Estimate')renderApprovedEstimate(content,p);
    }
    names.forEach(name=>{const b=button(name,()=>show(name),tabs);b.setAttribute('role','tab');});
    const requestedInvoice=invoiceRows(p.id).find(i=>String(i.id)===query.get('invoice'));
    show(requestedInvoice?'Invoices':names[0]);
    if(requestedInvoice)invoiceDetail(requestedInvoice);
  }
  function renderSubcontractors(content,p,refresh) {
    content.innerHTML+=table(['Name','Trade','Account Email','Actions'],(p.subcontractors||[]).map((s,i)=>`<tr><td>${E(s.name)}</td><td>${E(s.trade)}</td><td>${E(s.email || (s.name==='Demo Subcontractor'?'demo.subcontractor@buffbison.com':'Not linked'))}</td><td><button type="button" class="btn-outline" data-remove-assignment="${i}">Remove</button></td></tr>`));
    content.querySelectorAll('[data-remove-assignment]').forEach(b=>b.onclick=()=>{
      if(!confirm('Remove this subcontractor from the project?'))return;
      try { const next={...p,subcontractors:p.subcontractors.filter((_,i)=>i!==Number(b.dataset.removeAssignment))};D.saveProject(next);Object.assign(p,next);refresh(); }catch(err){alert(err.message);}
    });
    button('Assign Subcontractor',()=>{
      const el=dialog('Assign Subcontractor',`<form>${field('Name','name','Demo Subcontractor')}${field('Account email','email','demo.subcontractor@buffbison.com','email')}<p>Use the subcontractor’s login email to show this project in their portal.</p>${field('Trade','trade')}<p data-error class="portal-error" role="alert"></p><button type="submit" class="btn">Assign</button></form>`);
      el.querySelector('form').onsubmit=ev=>{
        ev.preventDefault();
        try {
          const f=ev.target.elements;
          const entry={name:f.name.value.trim(),email:f.email.value.trim().toLowerCase(),trade:f.trade.value.trim()};
          if(!entry.name||!entry.trade)throw Error('Enter a name and trade.');
          const list=[...(p.subcontractors||[])];
          const index=list.findIndex(s=>(s.email|| (s.name==='Demo Subcontractor'?'demo.subcontractor@buffbison.com':'')).toLowerCase()===entry.email);
          if(index<0)list.push(entry);else list[index]=entry;
          const next={...p,subcontractors:list};D.saveProject(next);Object.assign(p,next);el.close();refresh();
        }catch(err){error(el,err);}
      };
    },content);
  }
  function renderApprovedEstimate(target,p,selectedEstimate=null) {
    const estimate=selectedEstimate || p.estimate || (p.id===1?{estimate_number:'EST-RIVERSTONE',status:'Approved',line_items:[{description:'Materials',quantity:1,unit_cost:21000},{description:'Labor',quantity:1,unit_cost:15000},{description:'Equipment',quantity:1,unit_cost:2500},{description:'Subcontractors',quantity:1,unit_cost:7500},{description:'Permits',quantity:1,unit_cost:1000},{description:'Miscellaneous',quantity:1,unit_cost:1500}]}:null);
    if(!estimate){target.innerHTML+='<p>No approved estimate attached to this project.</p>';return;}
    target.innerHTML+=`<p>${E(estimate.estimate_number)} · ${E(estimate.status||'Approved')} · ${E(p.client)}</p>`+table(['Description','Quantity','Unit cost','Line total'],estimate.line_items.map(l=>`<tr><td>${E(l.description)}</td><td>${l.quantity}</td><td>${M(l.unit_cost)}</td><td>${M(l.quantity*l.unit_cost)}</td></tr>`))+`<h3>Total ${M(estimate.line_items.reduce((s,l)=>s+l.quantity*l.unit_cost,0))}</h3>`;
  }
  function clientEstimates() {
    const p=D.visibleProjects()[0];
    const list=[p.estimate, ...window.CLIENT_DEMO.estimates.slice(1)];
    main.innerHTML='';main.append(banner);
    const section=document.createElement('section');section.className='card';
    section.innerHTML='<h2>Your Estimates</h2>'+table(['Estimate','Project','Date','Amount','Status','Details'],list.map((e,i)=>`<tr><td>${E(e.title||e.estimate_number)}</td><td>${E(p.name)}</td><td>${E(e.date||'2026-10-12')}</td><td>${M(e.line_items.reduce((s,l)=>s+l.quantity*l.unit_cost,0))}</td><td>${E(e.status)}</td><td><button type="button" class="btn-outline" data-estimate="${i}">View</button></td></tr>`));
    section.querySelectorAll('[data-estimate]').forEach(b=>b.onclick=()=>{const e=list[Number(b.dataset.estimate)];const el=dialog(e.title||e.estimate_number,'<div data-estimate-detail></div>');renderApprovedEstimate(el.querySelector('[data-estimate-detail]'),p,e);});
    main.append(section);
    const approved=document.createElement('section');approved.className='card';approved.innerHTML='<h2>Approved Estimate Details</h2>';renderApprovedEstimate(approved,p);main.append(approved);
  }
  async function readFile(file,photo) {
    if(file.size>2*1024*1024)throw Error('Choose a file smaller than 2 MB for this browser demo.');
    if(!(photo?/\.(png|jpe?g|gif|webp)$/i:/\.(pdf|png|jpe?g|gif|webp|txt|csv|docx?|xlsx?)$/i).test(file.name))throw Error('Choose a supported file type.');
    return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve({name:file.name,data:reader.result});reader.onerror=()=>reject(Error('Could not read the file.'));reader.readAsDataURL(file);});
  }
  function attachmentForm(projectId,photo,done) {
    const el=dialog(photo?'Upload Progress Photo':'Attach Document',`<form><label>Project<select name="project" required>${options(projectId)}</select></label>${field('Title','title')}<label>File (up to 2 MB)<input type="file" name="file" accept="${photo?'.png,.jpg,.jpeg,.gif,.webp':'.pdf,.png,.jpg,.jpeg,.txt,.csv,.doc,.docx,.xls,.xlsx'}" required></label>${photo?'':'<label>Type<select name="type"><option>Receipt</option><option>Contract</option><option>Other</option></select></label>'}<p data-error class="portal-error" role="alert"></p><button type="submit" class="btn">Save Attachment</button></form>`);
    el.querySelector('form').onsubmit=async ev=>{ev.preventDefault();const f=ev.target.elements;try{const file=await readFile(f.file.files[0],photo),list=D.read('files',[]);list.push({...file,id:Date.now(),project_id:Number(f.project.value),title:f.title.value,photo,type:photo?'Photo':f.type.value,date:D.today()});D.write('files',list);el.close();done();}catch(err){error(el,err);}};
  }
  function renderFiles(target,projectId,photo) {
    const list=D.read('files',[]).filter(f=>f.photo===photo&&(!projectId||f.project_id===projectId)&&D.visibleProjects().some(p=>p.id===f.project_id));
    target.innerHTML=list.length?(photo?'<div class="portal-gallery">'+list.map(f=>`<article><img src="${E(f.data)}" alt="${E(f.title)}"><h3>${E(f.title)}</h3><p>${E(D.projects().find(p=>p.id===f.project_id)?.name)}</p><a href="${E(f.data)}" download="${E(f.name)}">Download photo</a></article>`).join('')+'</div>':table(['Title','Project','Type','File'],list.map(f=>`<tr><td>${E(f.title)}</td><td>${E(D.projects().find(p=>p.id===f.project_id)?.name)}</td><td>${E(f.type)}</td><td><a href="${E(f.data)}" download="${E(f.name)}">${E(f.name)}</a></td></tr>`))):'<p class="portal-empty">No attachments yet.</p>';
  }
  function uploads() {
    const photo=path.includes('photos'), input=document.querySelector('[name=project_name]');
    if(input){const select=document.createElement('select');select.id=input.id;select.name=input.name;select.required=true;select.innerHTML='<option value="">Select a project</option>'+D.visibleProjects().map(p=>`<option>${E(p.name)}</option>`).join('');input.replaceWith(select);
      const form=select.closest('form');form.onsubmit=async ev=>{ev.preventDefault();try{const file=await readFile(form.querySelector('input[type=file]').files[0],photo);const p=D.visibleProjects().find(p=>p.name===select.value);if(!p)throw Error('Select a project.');const list=D.read('files',[]);list.push({...file,id:Date.now(),project_id:p.id,title:form.querySelector('[name=title]')?.value||file.name,photo,type:photo?'Photo':form.document_type.value,date:D.today()});D.write('files',list);location.href=photo?'/photos':'/documents';}catch(err){alert(err.message);}};
      const file=form.querySelector('input[type=file]');if(!photo)file.accept+=',.png,.jpg,.jpeg,.webp';
    }else{
      const section=document.createElement('section');section.className='card';section.innerHTML='<h2>Browser Demo Attachments</h2><label>Project <select data-file-filter><option value="">All projects</option>'+options()+'</select></label><div data-files></div>';main.append(section);
      const filter=section.querySelector('select');const render=()=>renderFiles(section.querySelector('[data-files]'),Number(filter.value)||null,photo);filter.onchange=render;render();
      const existing=document.querySelector('#project-filter');if(existing)existing.onchange=()=>document.querySelectorAll('.photo-box').forEach(box=>box.hidden=existing.selectedIndex>0&&!box.textContent.includes(existing.value));
    }
  }
  function search() {
    const input=document.querySelector('.header input[type=search]');if(!input||role!=='employee')return;
    input.setAttribute('aria-label','Search client names, project names, or invoice numbers');
    const results=document.createElement('section');results.className='card search-results';results.hidden=true;main.insertBefore(results,banner.nextSibling);
    input.oninput=()=>{const q=input.value.trim().toLowerCase();results.hidden=!q;if(!q)return;const found=[];D.projects().filter(p=>(p.name+' '+p.client).toLowerCase().includes(q)).forEach(p=>found.push(`<a href="${projectLink(p)}">Project: ${E(p.name)} · Client: ${E(p.client)}</a>`));D.invoices().filter(i=>i.number.toLowerCase().includes(q)).forEach(i=>found.push(`<a href="/project/${i.project_id}?invoice=${i.id}">Invoice #${E(i.number)} · ${M(invoiceTotal(i))}</a>`));results.innerHTML='<h2>Search Results</h2>'+(found.join('')||'<p>No matching projects, clients, or invoices.</p>');};
  }
  function newProject() {
    const form=document.querySelector('form.form-page');if(!form)return;
    form.onsubmit=ev=>{ev.preventDefault();try{const f=form.elements;if(f.start_date.value&&f.end_date.value&&f.end_date.value<f.start_date.value)throw Error('Completion date cannot precede start date.');const p=D.saveProject({name:f.project_name.value.trim(),client:f.client_name.value.trim(),email:f.client_email.value,phone:f.client_phone.value,address:f.address.value,type:f.project_type.value,description:f.description.value,manager:f.manager.value,start:f.start_date.value,due:f.end_date.value,budget:Number(f.budget.value||0),actual:0,progress:0,status:f.status.value});location.href=projectLink(p);}catch(err){alert(err.message);}};
  }
  function dashboard() {
    main.innerHTML='';main.append(banner);
    const list=D.visibleProjects(), invoices=invoiceRows(), tasks=D.read('tasks',[]).filter(t=>list.some(p=>p.id===t.project_id)&&t.status!=='Completed');
    const cards=document.createElement('section');cards.className='cards';cards.innerHTML=[['Projects',list.length],['Unpaid Invoices',M(invoices.filter(i=>i.status!=='Paid').reduce((s,i)=>s+invoiceTotal(i),0))],['Upcoming Tasks',tasks.length]].map(([label,value])=>`<div class="card summary"><p class="summary-label">${label}</p><p class="summary-value">${value}</p></div>`).join('');main.append(cards);
    const section=document.createElement('section');section.className='card';section.innerHTML='<h2>'+ (role==='employee'?'Projects':'Your Projects')+'</h2>'+table(['Project','Client','Status','Progress','Due'],list.map(p=>`<tr><td><a class="project-name-link" href="${projectLink(p)}">${E(p.name)}</a></td><td>${E(p.client)}</td><td>${E(p.status)}</td><td>${p.progress||0}%</td><td>${E(p.due)}</td></tr>`));main.append(section);
    const actions=document.createElement('div');actions.className='portal-actions';section.append(actions);
    if(role==='subcontractor'){button('Submit Invoice',()=>invoiceForm(),actions,'btn');button('Upload Progress Photo',()=>attachmentForm(1,true,()=>dashboard()),actions);}
    if(role==='client'){
      const estimates=document.createElement('section');estimates.className='card';estimates.innerHTML='<h2>Approved Estimate</h2>';renderApprovedEstimate(estimates,list[0]);main.append(estimates);
      const updates=document.createElement('section');updates.className='card';updates.innerHTML='<h2>Recent Project Updates</h2>'+table(['Date','Update'],window.CLIENT_DEMO.activity.map(a=>`<tr><td>${E(a.date)}</td><td>${E(a.text)}</td></tr>`))+'<a class="btn-outline" href="/client/estimates">Review Estimates</a>';main.append(updates);
    }
    const due=document.createElement('section');due.className='card';due.innerHTML='<h2>Upcoming Tasks</h2>'+table(['Task','Project','Due','Status'],tasks.slice().sort((a,b)=>a.due_date.localeCompare(b.due_date)).map(t=>`<tr><td>${E(t.name)}</td><td>${E(list.find(p=>p.id===t.project_id)?.name)}</td><td>${E(t.due_date)}</td><td>${E(t.status)}</td></tr>`));main.append(due);
    const inv=document.createElement('section');inv.className='card';inv.innerHTML='<h2>Invoices</h2><div data-invoice-list></div>';main.append(inv);renderInvoices();
  }
  function assignedProjects(){const body=main.querySelector('tbody');if(body)body.innerHTML=D.visibleProjects().map(p=>`<tr><td>${E(p.name)}</td><td>${E(p.status)}</td><td>${p.progress||0}%</td><td>${E(p.due)}</td><td><a href="${projectLink(p)}" class="btn-outline">View</a></td></tr>`).join('');}
  if(path.endsWith('/invoices'))invoicePage();
  else if(path==='/projects'&&role==='subcontractor'&&new URLSearchParams(location.search).has('project'))projectDetails();
  else if(path==='/projects'&&role==='employee')projectList();
  else if(path==='/projects'||path==='/client/my-projects')assignedProjects();
  else if(path==='/dashboard')dashboard();
  else if(/^\/project\/\d+$/.test(path))projectDetails();
  else if(path==='/new-project')newProject();
  else if(path.startsWith('/photos')||path.startsWith('/documents'))uploads();
  else if(path==='/client/estimates')clientEstimates();
  search();
})();
