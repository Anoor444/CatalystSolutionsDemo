/* Shared, browser-only demo records. These are not server authorization rules. */
window.Demo = (() => {
  const prefix = 'buffbison.frontend.v1.';
  function read(key, fallback) {
    try { const value = JSON.parse(localStorage.getItem(prefix + key)); return value ?? fallback; }
    catch { return fallback; }
  }
  function write(key, value) {
    try { localStorage.setItem(prefix + key, JSON.stringify(value)); }
    catch { throw new Error('Browser storage is full or unavailable. Remove a large attachment and try again.'); }
    return value;
  }
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => Number(value || 0).toLocaleString('en-US', {style:'currency',currency:'USD'});
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
  function projects() {
    const list = read('projects', window.DEMO_PROJECTS || []);
    if (window.portalContext.role !== 'client') return list;
    return list.map(p => p.id === 1 ? {...p,
      description:p.description || window.CLIENT_DEMO.project.description,
      address:p.address || window.CLIENT_DEMO.project.address,
      estimate:p.estimate || window.CLIENT_DEMO.estimates[0]
    } : p);
  }
  function saveProject(project) {
    const list = projects();
    if (!project.id) project.id = Math.max(12, ...list.map(p => p.id)) + 1;
    const index = list.findIndex(p => p.id === project.id);
    if (index < 0) list.push(project); else list[index] = project;
    write('projects', list); return project;
  }
  function visibleProjects() {
    const role = window.portalContext.role;
    const email = String(window.portalContext.user || '').trim().toLowerCase();
    const name = String(window.portalContext.name || '').trim().toLowerCase();
    return projects().filter(p => role === 'employee' || (role === 'client' ? p.id === 1 :
      (p.subcontractors || []).some(s => s.email
        ? s.email.trim().toLowerCase() === email
        : email === 'demo.subcontractor@buffbison.com' && s.name.trim().toLowerCase() === (name || 'demo subcontractor'))));
  }
  function actualCost(project) {
    const costs = read('costs', null);
    if (!costs) return Number(project.actual || 0);
    const expenses = (costs.expenses || []).filter(e => e.project_id === project.id);
    // An empty ledger is zero only when this project has cost-tracking records.
    const tracked = expenses.length || (costs.estimates || []).some(e => e.project_id === project.id)
      || (costs.projects || []).some(p => p.id === project.id);
    return tracked ? expenses.reduce((sum, e) => sum + Number(e.amount || 0), 0) : Number(project.actual || 0);
  }
  function invoices() {
    const list = read('invoices', [
      {id:1042, number:'1042', project_id:1, date:'2026-10-15', due:'2026-11-15', status:'Unpaid', kind:'client', lines:[{description:'Kitchen remodel progress payment',quantity:1,rate:8250}]},
      {id:1038, number:'1038', project_id:1, date:'2026-10-10', due:'2026-10-25', status:'Paid', kind:'client', lines:[{description:'Cabinet deposit',quantity:1,rate:4100}]},
      {id:2101, number:'SC-2026-101', project_id:1, date:'2026-10-28', due:'2026-11-28', status:'Pending Approval', kind:'subcontractor', lines:[{description:'Installation labor',quantity:1,rate:4800}]}
    ]);
    if (window.portalContext.role !== 'client') return list;
    return [...list, ...window.CLIENT_DEMO.invoices.filter(sample => !list.some(i => i.id === sample.id || i.number === sample.number))];
  }
  function download(name, blob) {
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function pdf(invoice) {
    const p = projects().find(p => p.id === invoice.project_id);
    const total = invoice.lines.reduce((s,l) => s + l.quantity*l.rate,0);
    const text = ['BUFF BISON CONSTRUCTION', `Invoice #${invoice.number}`, p?.name || '', `Client: ${p?.client || ''}`, `Date: ${invoice.date}   Due: ${invoice.due}`, `Status: ${invoice.status}`, '', ...invoice.lines.map(l => `${l.description} | ${l.quantity} x ${money(l.rate)} = ${money(l.quantity*l.rate)}`), '', `TOTAL: ${money(total)}`];
    const clean = s => s.replace(/[^\x20-\x7e]/g,'?').replace(/([\\()])/g,'\\$1');
    const wrapped = text.flatMap(s => s.match(/.{1,78}/g) || ['']);
    const pages = [];
    for (let i=0; i<wrapped.length; i+=40) pages.push(wrapped.slice(i,i+40));
    const objects = ['<< /Type /Catalog /Pages 2 0 R >>',`<< /Type /Pages /Kids [${pages.map((_,i)=>`${4+i*2} 0 R`).join(' ')}] /Count ${pages.length} >>`,'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
    pages.forEach((lines,i) => {
      const stream = `BT /F1 12 Tf 45 795 Td 18 TL ${lines.map((s,n) => `${n?'T* ':''}(${clean(s)}) Tj`).join('\n')} ET`;
      objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 3 0 R >> >> /Contents ${5+i*2} 0 R >>`,`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
    });
    let output = '%PDF-1.4\n', offsets = [0];
    objects.forEach((o,i) => { offsets.push(output.length); output += `${i+1} 0 obj\n${o}\nendobj\n`; });
    const start = output.length;
    output += `xref\n0 ${objects.length+1}\n0000000000 65535 f \n${offsets.slice(1).map(n => String(n).padStart(10,'0')+' 00000 n \n').join('')}trailer\n<< /Size ${objects.length+1} /Root 1 0 R >>\nstartxref\n${start}\n%%EOF`;
    download(`Invoice-${invoice.number}.pdf`, new Blob([output],{type:'application/pdf'}));
  }
  if (!read('costs', null)) write('costs', window.DEMO_COSTS);
  if (!read('tasks', null)) write('tasks', window.DEMO_TASKS);
  return {read,write,esc,money,today,projects,saveProject,visibleProjects,actualCost,invoices,download,pdf};
})();
