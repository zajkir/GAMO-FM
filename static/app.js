const APP_BRAND=(window.GAMO_CONTEXT&&window.GAMO_CONTEXT.brandName)||'GAMO a.s.';
const APP_ORG_CODE=(window.GAMO_CONTEXT&&window.GAMO_CONTEXT.orgCode)||'GAMO';
const defs={
building:[['code','Kód budovy','A'],['name','Názov budovy',''],['address','Adresa',''],['manager','Správca','Facility Management'],{name:'floors_count',label:'Počet podlaží pre 3D model',type:'number',value:'3',min:'0',max:'50'}],
floor:[{name:'building_id',label:'Budova',type:'building',required:true},['code','Kód podlažia','1.NP'],['name','Názov','Prízemie']],
room:[{name:'floor_id',label:'Podlažie',type:'floor',required:true},['code','Kód miestnosti','A101'],['name','Názov','Kancelária'],{name:'area',label:'Plocha m²',type:'number',value:'25',step:'0.01',min:'0'},['tenant','Nájomca',APP_BRAND],['zone','Zóna','']],
asset:[
 {name:'asset_id',label:'Asset ID',type:'text',value:'',required:false,placeholder:'Automaticky podľa profesie'},['name','Názov zariadenia',''],
 {name:'building_id',label:'Budova',type:'building',required:true},
 {name:'floor_id',label:'Podlažie',type:'floor',required:true},
 {name:'room_id',label:'Miestnosť',type:'room',required:true},
 {name:'profession',label:'Profesia',value:'HVAC',required:true},
 {name:'grp',label:'Skupina',value:'VRV systém',required:true},
 {name:'type',label:'Typ',value:'VRV-IN',required:true},
 ['manufacturer','Výrobca',''],['model','Model',''],['serial','Výrobné číslo',''],['system_id','System ID',''],
 {name:'parent_id',label:'Parent Asset',type:'asset',value:'',required:false,optionalLabel:'Bez parent assetu'},
 {name:'status',label:'Stav',type:'select',options:['Prevádzka','Mimo prevádzky','Servis','Porucha','Vyradené'],value:'Prevádzka',required:true},
 {name:'criticality',label:'Kritickosť',type:'select',options:['A','B','C'],value:'B',required:true},
 {name:'service_months',label:'Servis interval mes.',type:'number',value:'6',min:'0'},
 {name:'revision_months',label:'Revízia interval mes.',type:'number',value:'12',min:'0'},
 {name:'purchase_price',label:'Cena €',type:'number',value:'0',min:'0',step:'0.01'},
 ['ip','IP adresa',''],['protocol','Protokol',''],['notes','Poznámka','']
],
workorder:[
 {name:'asset_id',label:'Asset',type:'asset',value:currentAsset||'',required:true},
 {name:'title',label:'Názov pracovného príkazu',type:'select',options:['Preventívna údržba','Pravidelná revízia','Oprava poruchy','Havarijný zásah','Výmena zariadenia','Diagnostika','Kontrola zariadenia'],value:'Preventívna údržba',required:true},
 {name:'kind',label:'Typ zásahu',type:'select',options:['PM','REV','OPR','VYM'],value:'PM',required:true},
 {name:'priority',label:'Priorita',type:'select',options:['Nízka','Stredná','Vysoká','Kritická'],value:'Stredná',required:true},
 {name:'status',label:'Stav',type:'select',options:['Plánované','Pridelené','Prebieha','Pozastavené','Ukončené','Zrušené'],value:'Plánované',required:true},
 {name:'due',label:'Termín',type:'date',value:''},['supplier','Dodávateľ',''],['technician','Technik',''],
 {name:'cost',label:'Náklad €',type:'number',value:'0',min:'0',step:'0.01'},['description','Popis','']
],
incident:[
 {name:'asset_id',label:'Asset',type:'asset',value:currentAsset||'',required:true},['title','Názov incidentu',''],
 {name:'severity',label:'Závažnosť',type:'select',options:['Nízka','Stredná','Vysoká','Kritická','Havária'],value:'Stredná',required:true},
 {name:'status',label:'Stav',type:'select',options:['Otvorená','Pridelená','Rieši sa','Čaká na diel','Vyriešená','Ukončená'],value:'Otvorená',required:true},
 {name:'reported',label:'Nahlásené',type:'date',value:new Date().toISOString().slice(0,10)},['impact','Dopad',''],['cause','Príčina',''],
 {name:'cost',label:'Náklad €',type:'number',value:'0',min:'0',step:'0.01'}
],
user:[['name','Meno',''],['email','E-mail',''],{name:'role',label:'Rola',type:'select',options:['Administrator','Facility Manager','Technik','Servisný technik','Viewer'],value:'Technik',required:true},{name:'status',label:'Stav používateľa',type:'select',options:['Aktívny','Neaktívny'],value:'Aktívny',required:true},{name:'password',label:'Dočasné heslo',type:'password',value:'',required:true}]
}
function fieldDef(a){return Array.isArray(a)?{name:a[0],label:a[1],value:a[2],type:(a[0]=='password'?'password':'text')} : a}
function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
function safeInternalUrl(value){const v=String(value||'/');return v.startsWith('/')&&!v.startsWith('//')?v:'/'}
async function fetchJson(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw new Error(url);return r.json()}
function setPicker(select,items,preferred,placeholder,labelFn,optional=false){
 select.disabled=false;
 const first=optional?'<option value="">'+escapeHtml(placeholder)+'</option>':'<option value="">'+escapeHtml(placeholder)+'</option>';
 select.innerHTML=first+items.map(x=>'<option value="'+x.id+'" '+(String(x.id)===String(preferred)?'selected':'')+'>'+escapeHtml(labelFn(x))+'</option>').join('');
 if(!items.length){select.innerHTML='<option value="">Žiadne dostupné záznamy</option>';select.disabled=true}
}
async function loadBuildingOptions(select,preferred=''){
 select.disabled=true;select.innerHTML='<option>Načítavam budovy…</option>';
 try{const items=await fetchJson('/api/buildings/options');setPicker(select,items,preferred,'Vyber budovu…',x=>[x.code,x.name].filter(Boolean).join(' · '))}
 catch(e){select.innerHTML='<option value="">Budovy sa nepodarilo načítať</option>';select.disabled=true}
}
async function loadFloorOptions(select,preferred=''){
 select.disabled=true;select.innerHTML='<option>Načítavam podlažia…</option>';
 try{const items=await fetchJson('/api/floors/options');setPicker(select,items,preferred,'Vyber podlažie…',x=>[x.building_code,x.code,x.name].filter(Boolean).join(' · '))}
 catch(e){select.innerHTML='<option value="">Podlažia sa nepodarilo načítať</option>';select.disabled=true}
}
async function loadFloorsForBuilding(select,buildingId,preferred=''){
 if(!buildingId){select.innerHTML='<option value="">Najprv vyber budovu</option>';select.disabled=true;return}
 select.disabled=true;select.innerHTML='<option>Načítavam podlažia…</option>';
 try{const items=await fetchJson('/api/floors/'+buildingId);setPicker(select,items,preferred,'Vyber podlažie…',x=>[x.code,x.name].filter(Boolean).join(' · '))}
 catch(e){select.innerHTML='<option value="">Podlažia sa nepodarilo načítať</option>';select.disabled=true}
}
async function loadRoomsForFloor(select,floorId,preferred=''){
 if(!floorId){select.innerHTML='<option value="">Najprv vyber podlažie</option>';select.disabled=true;return}
 select.disabled=true;select.innerHTML='<option>Načítavam miestnosti…</option>';
 try{const items=await fetchJson('/api/rooms/'+floorId);setPicker(select,items,preferred,'Vyber miestnosť…',x=>[x.code,x.name,(x.area?x.area+' m²':'')].filter(Boolean).join(' · '))}
 catch(e){select.innerHTML='<option value="">Miestnosti sa nepodarilo načítať</option>';select.disabled=true}
}
async function loadAssetOptions(select,preferred='',optional=false,exclude=''){
 select.disabled=true;select.innerHTML='<option>Načítavam assety…</option>';
 try{
  let items=await fetchJson('/api/assets/options');
  if(exclude)items=items.filter(x=>String(x.id)!==String(exclude));
  setPicker(select,items,preferred,optional?'Bez parent assetu':'Vyber zariadenie…',x=>{
   const location=[x.building,x.room].filter(Boolean).join(' / ');
   return [x.asset_id,x.name,location].filter(Boolean).join(' · ')
  },optional);
  if(!items.length){
   const note=document.createElement('small');note.className='asset-picker-note';note.innerHTML='V organizácii zatiaľ nie je žiadny asset. <a href="/assets">Otvoriť Asset register →</a>';select.parentElement.appendChild(note)
  }
 }catch(e){select.innerHTML='<option value="">Assety sa nepodarilo načítať</option>';select.disabled=true}
}
async function wireRecordPickers(host){
 const building=host.querySelector('select[name="building_id"]');
 const floor=host.querySelector('select[name="floor_id"]');
 const room=host.querySelector('select[name="room_id"]');
 const assets=[...host.querySelectorAll('select[data-picker="asset"]')];
 if(building&&floor){
  await loadBuildingOptions(building,building.dataset.preferred||'');
  await loadFloorsForBuilding(floor,building.value,floor.dataset.preferred||'');
  if(room)await loadRoomsForFloor(room,floor.value,room.dataset.preferred||'');
  building.addEventListener('change',async()=>{await loadFloorsForBuilding(floor,building.value);if(room)await loadRoomsForFloor(room,floor.value)});
  if(room)floor.addEventListener('change',()=>loadRoomsForFloor(room,floor.value));
 }else if(building){
  await loadBuildingOptions(building,building.dataset.preferred||'');
 }else if(floor){
  await loadFloorOptions(floor,floor.dataset.preferred||'');
 }
 for(const s of assets)await loadAssetOptions(s,s.dataset.preferred||'',s.dataset.optional==='1',s.dataset.exclude||'');
}
function modal(t,editData=null){
 const f=defs[t],host=document.querySelector('#fields');if(!f||!host)return;
 const editing=!!(editData&&editData.id);let h='<div class="formgrid">';
 f.forEach((raw,i)=>{
  const a={...fieldDef(raw)};
  if(editing&&Object.prototype.hasOwnProperty.call(editData,a.name))a.value=editData[a.name]??'';
  if(editing&&((t==='building'&&a.name==='floors_count')||(t==='floor'&&a.name==='building_id')||(t==='room'&&a.name==='floor_id')))return;
  const full=['notes','description','impact','cause'].includes(a.name)?'full':'';let control;
  const required=(a.required===true||((a.required!==false)&&i<2))?' required':'';
  if(a.type==='select'){
   const opts=[...(a.options||[])];if(editing&&a.value&&!opts.includes(a.value))opts.unshift(a.value);
   control=`<select name="${a.name}"${required}>${opts.map(o=>`<option value="${escapeHtml(o)}" ${String(o)===String(a.value)?'selected':''}>${escapeHtml(o)}</option>`).join('')}</select>`;
  }else if(a.type==='asset'){
   control=`<select class="asset-picker" data-picker="asset" data-optional="${a.required===false?'1':'0'}" data-exclude="${editing&&t==='asset'&&a.name==='parent_id'?escapeHtml(editData.id):''}" name="${a.name}" data-preferred="${escapeHtml(a.value||'')}"${required}><option>Načítavam assety…</option></select>`;
  }else if(['building','floor','room'].includes(a.type)){
   control=`<select class="location-picker" name="${a.name}" data-preferred="${escapeHtml(a.value||'')}"${required}><option>Načítavam…</option></select>`;
  }else{
   const attrs=[a.min!==undefined?`min="${escapeHtml(a.min)}"`:'',a.max!==undefined?`max="${escapeHtml(a.max)}"`:'',a.step!==undefined?`step="${escapeHtml(a.step)}"`:'',a.placeholder?`placeholder="${escapeHtml(a.placeholder)}"`:'',a.name==='password'?'minlength="10" autocomplete="new-password"':''].filter(Boolean).join(' ');
   control=`<input type="${a.type||'text'}" name="${a.name}" value="${escapeHtml(a.value??'')}"${required} ${attrs}>`;
  }
  h+=`<div class="field ${full}"><label>${escapeHtml(a.label)}</label>${control}</div>`;
 });
 h+='</div>';host.innerHTML=h;wireRecordPickers(host);
 const form=document.querySelector('#mform');form.action=editing?'/edit/'+t+'/'+editData.id:'/add/'+t;form.method='post';
 const createTitles={user:'Nový používateľ',incident:'Nahlásiť nový incident',workorder:'Nový pracovný príkaz',asset:'Nový asset',building:'Nová budova',floor:'Nové podlažie',room:'Nová miestnosť'};
 const editTitles={incident:'Upraviť incident',workorder:'Upraviť pracovný príkaz',asset:'Upraviť asset',building:'Upraviť budovu',floor:'Upraviť podlažie',room:'Upraviť miestnosť'};
 const meta={asset:['◇','ASSET REGISTER','Evidencia technického zariadenia, jeho umiestnenia, väzieb a servisných parametrov.'],building:['▦','FACILITY STRUCTURE','Správa objektu v portfóliu '+APP_BRAND],floor:['▤','FACILITY STRUCTURE','Správa podlažia a jeho názvu.'],room:['□','SPACE MANAGEMENT','Správa miestnosti, plochy, nájomcu a prevádzkovej zóny.'],workorder:['✓','MAINTENANCE CONTROL','Údržba, revízie, opravy a servisný workflow konkrétneho zariadenia.'],incident:['!','INCIDENT CONTROL','Evidencia a riadenie poruchy alebo havárie.'],user:['⌾','IDENTITY & ACCESS','Vytvorenie používateľského účtu, roly a prístupu do platformy.']};
 const m=meta[t]||['＋','GAMO OPERATIONS','Správa záznamu v '+APP_BRAND];
 document.querySelector('#mtitle').textContent=editing?(editTitles[t]||'Upraviť záznam'):(createTitles[t]||'Nový záznam');
 document.querySelector('#micon').textContent=m[0];document.querySelector('#mkicker').textContent=editing?'EDIT · '+m[1]:m[1];document.querySelector('#mdesc').textContent=m[2];
 const save=document.querySelector('#mform .modal-actions .primary');if(save)save.textContent=editing?'Uložiť zmeny':'Uložiť záznam';
 document.querySelector('#modal').classList.add('show');
 if(t==='asset'&&!editing){
  const aid=host.querySelector('input[name="asset_id"]'),profession=host.querySelector('input[name="profession"]');
  const preview=async()=>{if(!aid||aid.value.trim())return;try{const d=await fetchJson('/api/assets/next-id?profession='+encodeURIComponent(profession?.value||'ASSET'));aid.placeholder='Automaticky: '+d.asset_id}catch(e){aid.placeholder='Nechaj prázdne = automatické ID'}};
  preview();profession?.addEventListener('input',preview);profession?.addEventListener('change',preview);
 }
}
function editRecord(type,data){modal(type,data)}
function closeM(){document.querySelector('#modal').classList.remove('show')}function confirmAction(form,title='Odstrániť záznam?',detail='Táto akcia sa nedá jednoducho vrátiť späť.'){
 const m=document.querySelector('#confirmModal');if(!m)return window.confirm(title);
 window._gamoConfirmForm=form;
 const t=m.querySelector('#confirmTitle'),d=m.querySelector('#confirmDetail');if(t)t.textContent=title;if(d)d.textContent=detail;
 m.classList.add('show');return false;
}
function closeConfirm(){document.querySelector('#confirmModal')?.classList.remove('show');window._gamoConfirmForm=null}
function executeConfirm(){const f=window._gamoConfirmForm;if(!f)return;document.querySelector('#confirmModal')?.classList.remove('show');window._gamoConfirmForm=null;f.submit()}
function filterOpsRows(filter,btn){
 document.querySelectorAll('.ops-filter-btn').forEach(x=>x.classList.remove('active'));if(btn)btn.classList.add('active');
 document.querySelectorAll('[data-ops-row]').forEach(row=>{
  const status=row.dataset.status||'',severity=row.dataset.severity||'',priority=row.dataset.priority||'',overdue=row.dataset.overdue==='1';
  let show=filter==='all'||(filter==='active'&&!['Ukončené','Zrušené','Ukončená','Vyriešená'].includes(status))||(filter==='overdue'&&overdue)||(filter==='critical'&&(priority==='Kritická'||['Kritická','Havária'].includes(severity)))||(filter==='done'&&['Ukončené','Ukončená','Vyriešená'].includes(status));
  row.style.display=show?'':'none';
 });
}
function openTicketModal(){const m=document.querySelector('#ticketCreateModal');if(m){m.classList.add('show');setTimeout(()=>m.querySelector('input[name="subject"]')?.focus(),50)}}
function closeTicketModal(){document.querySelector('#ticketCreateModal')?.classList.remove('show')}
function filterTicketAssets(){
 const b=document.querySelector('#ticketBuilding'),a=document.querySelector('#ticketAsset');if(!a)return;
 const bid=b?.value||'';
 [...a.options].forEach((o,i)=>{if(i===0){o.hidden=false;return}o.hidden=!!bid&&o.dataset.building!==bid});
 if(a.selectedOptions[0]?.hidden)a.value='';
}

function updateTicketAttachmentLabel(input){
 const label=document.querySelector('#ticketAttachmentName');
 const file=input?.files?.[0];
 if(label)label.textContent=file?file.name:'';
}
function ticketInitials(name){
 return String(name||'??').trim().split(/\s+/).map(x=>x[0]||'').join('').slice(0,2).toUpperCase()||'??';
}
function ticketMessageElement(m){
 const row=document.createElement('div');row.className='ticket-message'+(m.mine?' mine':'')+(m.support?' support-message':'');row.dataset.messageId=m.id;
 const avatar=document.createElement('div');avatar.className='ticket-message-avatar';avatar.textContent=ticketInitials(m.sender_name);
 const body=document.createElement('div');body.className='ticket-message-body';
 const meta=document.createElement('div');
 const name=document.createElement('b');name.textContent=m.sender_name||'Systém';
 const role=document.createElement('span');role.textContent=m.sender_role||'Používateľ';
 const time=document.createElement('time');time.textContent=m.created||'';
 meta.append(name,role,time);
 const p=document.createElement('p');p.textContent=m.body||'';
 body.append(meta,p);
 if(Array.isArray(m.attachments)&&m.attachments.length){
  const files=document.createElement('div');files.className='ticket-attachments';
  m.attachments.forEach(a=>{
   const link=document.createElement('a');link.href=safeInternalUrl(a.url);link.setAttribute('download','');
   const icon=document.createElement('span');icon.textContent='⇩';
   const copy=document.createElement('div'),title=document.createElement('b'),metaFile=document.createElement('small');
   title.textContent=a.name||'Príloha';metaFile.textContent=((Number(a.size||0)/1024).toFixed(1))+' KB';
   copy.append(title,metaFile);link.append(icon,copy);files.appendChild(link);
  });
  body.appendChild(files);
 }
 row.append(avatar,body);return row;
}
function scrollTicketBottom(){
 const thread=document.querySelector('#ticketThread');if(thread){thread.scrollTop=thread.scrollHeight;document.querySelector('#ticketNewMessageHint')?.setAttribute('hidden','')}
}
async function refreshTicketMessages(forceScroll=false){
 const thread=document.querySelector('#ticketThread');if(!thread||document.hidden)return;
 if(thread.dataset.loading==='1')return;thread.dataset.loading='1';
 const ticketId=thread.dataset.ticketId,last=Number(thread.dataset.lastMessageId||0);
 const indicator=document.querySelector('#ticketLiveIndicator');
 try{
  const nearBottom=thread.scrollHeight-thread.scrollTop-thread.clientHeight<110;
  const res=await fetch('/api/ticket/'+encodeURIComponent(ticketId)+'/messages?after='+last,{cache:'no-store',headers:{'Accept':'application/json'}});
  if(!res.ok)throw new Error('HTTP '+res.status);
  const data=await res.json();
  (data.messages||[]).forEach(m=>thread.appendChild(ticketMessageElement(m)));
  if(data.last_id!==undefined)thread.dataset.lastMessageId=String(data.last_id);
  const count=document.querySelector('#ticketMessageCount');if(count){const n=thread.querySelectorAll('.ticket-message').length;count.textContent=n+' '+(n===1?'správa':(n>1&&n<5?'správy':'správ'))}
  const status=document.querySelector('#ticketLiveStatus');if(status&&data.status)status.textContent='● '+data.status;
  const updated=document.querySelector('#ticketUpdated');if(updated&&data.updated)updated.textContent=data.updated;
  if((data.messages||[]).length){
   if(forceScroll||nearBottom)scrollTicketBottom();else document.querySelector('#ticketNewMessageHint')?.removeAttribute('hidden');
   refreshNotifications(false);
  }
  if(indicator){indicator.classList.remove('offline');indicator.innerHTML='<i></i> LIVE'}
 }catch(e){
  if(indicator){indicator.classList.add('offline');indicator.innerHTML='<i></i> PRIPÁJAM…'}
 }finally{thread.dataset.loading='0'}
}
async function submitTicketReply(ev){
 ev.preventDefault();const form=ev.currentTarget,button=document.querySelector('#ticketReplyButton'),error=document.querySelector('#ticketReplyError');
 const textarea=form.querySelector('textarea[name="message"]');if(!textarea||!textarea.value.trim())return;
 if(button){button.disabled=true;button.classList.add('loading');button.innerHTML='Odosielam…'}
 if(error){error.hidden=true;error.textContent=''}
 try{
  const res=await fetch(form.action,{method:'POST',body:new FormData(form),headers:{'X-Requested-With':'GAMO-Live-Chat','Accept':'application/json'}});
  const data=await res.json().catch(()=>({}));
  if(!res.ok||!data.ok)throw new Error(data.error||'Správu sa nepodarilo odoslať.');
  textarea.value='';
  const attachment=form.querySelector('input[name="attachment"]');if(attachment)attachment.value='';
  const attachmentName=document.querySelector('#ticketAttachmentName');if(attachmentName)attachmentName.textContent='';
  await refreshTicketMessages(true);textarea.focus();
 }catch(e){
  if(error){error.textContent=e.message||'Správu sa nepodarilo odoslať.';error.hidden=false}
 }finally{
  if(button){button.disabled=false;button.classList.remove('loading');button.innerHTML='Odoslať <span>→</span>'}
 }
}
function initLiveTicket(){
 const thread=document.querySelector('#ticketThread');if(!thread)return;
 scrollTicketBottom();
 const form=document.querySelector('#ticketReplyForm');if(form){
  form.addEventListener('submit',submitTicketReply);
  form.querySelector('textarea')?.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();form.requestSubmit()}});
 }
 let running=false;
 const schedule=(delay=2500)=>{clearTimeout(window.GAMO_TICKET_TIMER);window.GAMO_TICKET_TIMER=setTimeout(async()=>{
  if(!document.hidden&&!running){running=true;try{await refreshTicketMessages(false)}finally{running=false}}
  schedule(document.hidden?20000:2500)
 },delay)};
 refreshTicketMessages(false).finally(()=>schedule());
 document.addEventListener('visibilitychange',()=>{if(!document.hidden){refreshTicketMessages(false);schedule(1800)}});
 window.addEventListener('beforeunload',()=>clearTimeout(window.GAMO_TICKET_TIMER));
}
function setTicketNavCount(value){
 let badge=document.querySelector('#ticketNavCount');
 const link=document.querySelector('.ticket-nav-link');
 const n=Math.max(0,Number(value||0));
 if(!badge&&link&&n){badge=document.createElement('b');badge.id='ticketNavCount';badge.className='nav-count';link.appendChild(badge)}
 if(badge){badge.textContent=n>99?'99+':String(n);badge.hidden=!n}
}
async function refreshTicketInboxState(initial=false){
 const list=document.querySelector('#ticketInboxList');if(!list||document.hidden)return;
 try{
  const res=await fetch('/api/tickets/inbox-state',{cache:'no-store',headers:{'Accept':'application/json'}});
  if(!res.ok)throw new Error('inbox');
  const data=await res.json();const previous=list.dataset.inboxVersion||'';
  setTicketNavCount(data.unread||0);
  const kpi=document.querySelector('#ticketInboxUnread');if(kpi)kpi.textContent=String(data.unread||0);
  if(initial||!previous){list.dataset.inboxVersion=data.version||'';return}
  if(String(data.version||'')!==String(previous)){
   document.querySelector('#ticketInboxRefreshHint')?.removeAttribute('hidden');
   document.title=document.title.startsWith('● ')?document.title:'● '+document.title;
  }
 }catch(_){}
}
function initTicketInboxWatch(){
 const list=document.querySelector('#ticketInboxList');if(!list)return;
 let running=false;
 refreshTicketInboxState(true);
 const tick=()=>{clearTimeout(window.GAMO_TICKET_INBOX_TIMER);window.GAMO_TICKET_INBOX_TIMER=setTimeout(async()=>{
  if(!running){running=true;try{await refreshTicketInboxState(false)}finally{running=false}}
  tick()
 },document.hidden?60000:15000)};
 tick();document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshTicketInboxState(false)});
 window.addEventListener('beforeunload',()=>clearTimeout(window.GAMO_TICKET_INBOX_TIMER));
}
let assetFilterTimer;
function filterRows(){
 clearTimeout(assetFilterTimer);
 assetFilterTimer=setTimeout(()=>{
  const input=document.querySelector('#search'),table=document.querySelector('#assettable');if(!input||!table)return;
  const v=input.value.trim().toLowerCase();
  table.querySelectorAll('tr').forEach((r,i)=>{
   if(!i)return;
   if(!r.dataset.searchText)r.dataset.searchText=(r.textContent||'').toLowerCase();
   r.style.display=!v||r.dataset.searchText.includes(v)?'':'none';
  });
 },90);
}
async function toggleDesktopFullscreen(){
 try{
  if(window.pywebview&&window.pywebview.api&&window.pywebview.api.toggle_fullscreen){
   const ok=await window.pywebview.api.toggle_fullscreen();
   if(ok!==false)return;
  }
  if(!document.fullscreenElement&&document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen();
  else if(document.fullscreenElement&&document.exitFullscreen)await document.exitFullscreen();
 }catch(e){console.warn('Fullscreen toggle failed',e)}
}
document.addEventListener('keydown',e=>{
 if(e.key==='F11'){e.preventDefault();toggleDesktopFullscreen()}
});

function toggleQuickSearch(){document.querySelector('#quickSearch').classList.toggle('showpanel');setTimeout(()=>document.querySelector('#globalSearchInput')?.focus(),50)}
const NOTIFICATION_READ_KEY='gamo_read_notifications_v1';
function notificationReadSet(){try{return new Set(JSON.parse(localStorage.getItem(NOTIFICATION_READ_KEY)||'[]'))}catch(e){return new Set()}}
function notificationTime(value){
 if(!value)return 'Práve teraz';
 let normalized=String(value).trim().replace(' ','T');if(!/[zZ]|[+-]\d\d:?\d\d$/.test(normalized))normalized+='Z';
 const d=new Date(normalized);if(Number.isNaN(d.getTime()))return value;
 const diff=Math.max(0,Math.floor((Date.now()-d.getTime())/1000));
 if(diff<60)return 'Práve teraz';if(diff<3600)return 'Pred '+Math.floor(diff/60)+' min';if(diff<86400)return 'Pred '+Math.floor(diff/3600)+' h';
 return d.toLocaleDateString('sk-SK')+' '+d.toLocaleTimeString('sk-SK',{hour:'2-digit',minute:'2-digit'});
}
function renderNotifications(items){
 const read=notificationReadSet(),list=document.querySelector('#notificationList');
 if(list)list.innerHTML=items.length?items.map(x=>{const seen=read.has(x.key),url=safeInternalUrl(x.url),level=['red','orange','blue','green'].includes(x.level)?x.level:'';return `<a class="searchitem notification-item ${seen?'notification-read':'notification-new'}" href="${url}"><div class="notification-copy"><b>${escapeHtml(x.title)}</b><small>${escapeHtml(x.subtitle)}</small><time data-notification-time="${escapeHtml(x.created_at||'')}">${escapeHtml(notificationTime(x.created_at))}</time></div><span class="badge ${level}">${escapeHtml(x.status)}</span></a>`}).join(''):'<div class="empty">Žiadne aktívne upozornenia.</div>';
 const unread=items.filter(x=>!read.has(x.key)).length,b=document.querySelector('#notificationBadge');
 if(b){b.textContent=unread>9?'9+':unread;b.hidden=!unread}
}
function markNotificationsRead(items){
 const read=notificationReadSet();items.forEach(x=>read.add(x.key));
 try{localStorage.setItem(NOTIFICATION_READ_KEY,JSON.stringify([...read].slice(-250)))}catch(e){}
 const b=document.querySelector('#notificationBadge');if(b)b.hidden=true;
}
function refreshNotificationTimes(){document.querySelectorAll('[data-notification-time]').forEach(el=>el.textContent=notificationTime(el.dataset.notificationTime))}
function refreshNotifications(render=false,markRead=false){return fetch('/api/notifications',{cache:'no-store'}).then(r=>r.json()).then(items=>{renderNotifications(items);if(markRead){markNotificationsRead(items);setTimeout(()=>renderNotifications(items),220)}return items}).catch(()=>{if(render){const l=document.querySelector('#notificationList');if(l)l.innerHTML='<div class="empty">Notifikácie sa nepodarilo načítať.</div>'}})}
function toggleNotifications(){let p=document.querySelector('#notifications');p.classList.toggle('showpanel');if(p.classList.contains('showpanel'))refreshNotifications(true,true)}
let searchTimer;function globalSearch(v){clearTimeout(searchTimer);let box=document.querySelector('#globalSearchResults');if(!box)return;if(v.trim().length<2){box.innerHTML='<div class="empty">Začni písať aspoň 2 znaky.</div>';return}searchTimer=setTimeout(()=>fetch('/api/search?q='+encodeURIComponent(v),{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('search');return r.json()}).then(items=>{box.innerHTML=items.length?items.map(x=>`<a class="searchitem" href="${safeInternalUrl(x.url)}"><b>${escapeHtml(x.title)}</b><small>${escapeHtml(x.subtitle)}</small><span>${escapeHtml(x.kind)}</span></a>`).join(''):'<div class="empty">Nenašli sa žiadne výsledky.</div>'}).catch(()=>{box.innerHTML='<div class="empty">Vyhľadávanie sa nepodarilo načítať.</div>'}),180)}
const configSchemas={
'Organizačná štruktúra':{icon:'▦',group:'ŠTRUKTÚRA OBJEKTOV',fields:[['Predvolený názov organizácie',APP_BRAND,'text'],['Kód lokality',APP_ORG_CODE,'text'],['Číslovanie podlaží','NP / PP','select',['NP / PP','Číselné','Vlastné']],['Prevádzkové zóny','Zapnuté','select',['Zapnuté','Vypnuté']]]},
'Technológie & číselníky':{icon:'◇',group:'ČÍSELNÍKY ASSETOV',fields:[['Predvolená profesia','HVAC','text'],['Stav nového assetu','Prevádzka','select',['Prevádzka','Servis','Mimo prevádzky']],['Kritickosť','B','select',['A','B','C']],['Výrobcovia','Spravované číselníkom','text']]},
'Asset ID generátor':{icon:'#',group:'IDENTIFIKÁCIA ASSETOV',fields:[['Maska Asset ID','{PROF}-000001','text'],['Počiatočné číslo','1','number'],['Dĺžka poradového čísla','6','number'],['Automatické generovanie','Zapnuté','select',['Zapnuté','Vypnuté']]]},
'Servis & SLA':{icon:'◷',group:'SERVISNÁ POLITIKA',fields:[['Predvolený PM interval (mesiace)','6','number'],['Revízny interval (mesiace)','12','number'],['Predvolená priorita','Stredná','select',['Nízka','Stredná','Vysoká','Kritická']],['SLA eskalácia','24 h','text']]},
'Notifikačné centrum':{icon:'◉',group:'NOTIFIKAČNÉ PRAVIDLÁ',fields:[['Upozorniť pred termínom','14 dní','text'],['Kritické incidenty','Okamžite','select',['Okamžite','Každú hodinu','Denne']],['E-mailové notifikácie','Zapnuté','select',['Zapnuté','Vypnuté']],['Systémové upozornenia','Zapnuté','select',['Zapnuté','Vypnuté']]]},
'Role & bezpečnosť':{icon:'⌾',group:'RIADENIE PRÍSTUPU',fields:[['Predvolená rola','Viewer','select',['Administrator','Facility Manager','Technik','Servisný technik','Viewer']],['Audit zmien','Zapnutý','select',['Zapnutý','Vypnutý']],['Vynútiť silné heslá','Áno','select',['Áno','Nie']],['Neaktívny účet','Blokovať prihlásenie','text']]},
'Import / Export':{icon:'⇩',group:'SPRÁVA DÁT',fields:[['Formát exportu','CSV','select',['CSV','XLSX','JSON']],['Kódovanie','UTF-8','text'],['Import duplicít','Preskočiť','select',['Preskočiť','Aktualizovať','Zastaviť']],['Audit importu','Zapnutý','select',['Zapnutý','Vypnutý']]]},
'Dokumentácia':{icon:'▤',group:'SPRÁVA DOKUMENTÁCIE',fields:[['Kategórie','Technická / Revízna / Servisná','text'],['Povolené prílohy','PDF, DOCX, XLSX, JPG, PNG','text'],['Verzovanie','Zapnuté','select',['Zapnuté','Vypnuté']],['Povinný popis','Áno','select',['Áno','Nie']]]},
'Zálohovanie':{icon:'▣',group:'POLITIKA ZÁLOHOVANIA',fields:[['Automatické zálohy','Denne','select',['Denne','Týždenne','Manuálne']],['Čas zálohy','02:00','time'],['Retencia','30 dní','text'],['Kontrola integrity','Zapnutá','select',['Zapnutá','Vypnutá']]]},
'Aktualizácie':{icon:'↻',group:'AKTUALIZAČNÝ KANÁL',fields:[['Kanál','Stable','select',['Stable','Preview','Manuálny']],['Automatická kontrola','Zapnutá','select',['Zapnutá','Vypnutá']],['Aktuálna verzia','9.0.0.5','text'],['Inštalácia','Po potvrdení','select',['Po potvrdení','Automaticky']]]},
'Relácie':{icon:'⌁',group:'BEZPEČNOSŤ RELÁCIÍ',fields:[['Čas relácie','8 hodín','text'],['Remember me','Povolené','select',['Povolené','Zakázané']],['Opätovné overenie admina','30 min','text'],['Odhlásiť pri neaktivite','Áno','select',['Áno','Nie']]]},
'Prevádzka systému':{icon:'⚙',group:'PREVÁDZKA SYSTÉMU',fields:[['Režim','Produkcia','select',['Produkcia','Údržba']],['Časové pásmo','Europe/Bratislava','text'],['Logovanie','Štandardné','select',['Minimálne','Štandardné','Detailné']],['Health monitoring','Zapnutý','select',['Zapnutý','Vypnutý']]]}
};
function configModal(title,desc){
 const schema=configSchemas[title]||{icon:'⚙',group:'SYSTÉMOVÁ KONFIGURÁCIA',fields:[['Hodnota','','text']]};
 document.querySelector('#configTitle').textContent=title;document.querySelector('#configDesc').textContent=desc;
 document.querySelector('#configSection').value=title;
 const box=document.querySelector('#configValue'); box.style.display='none';
 let host=document.querySelector('#configFields');
 if(!host){host=document.createElement('div');host.id='configFields';box.parentNode.insertBefore(host,box)}
 host.innerHTML='<div class="config-modal-hero"><span>'+schema.icon+'</span><div><small class="config-section-label">'+schema.group+'</small><b>'+title+'</b><p>'+desc+'</p></div></div><div class="config-field-grid">'+schema.fields.map((f,i)=>{let input=f[2]==='select'?'<select data-cfg="'+i+'">'+f[3].map(x=>'<option>'+x+'</option>').join('')+'</select>':'<input data-cfg="'+i+'" type="'+f[2]+'" value="'+f[1]+'">';return '<label><span>'+f[0]+'</span>'+input+'<small>'+(i===0?'Hlavné nastavenie tejto oblasti':'Upraviteľný systémový parameter')+'</small></label>'}).join('')+'</div>';
 fetch('/api/setting?section='+encodeURIComponent(title)).then(r=>r.json()).then(x=>{try{const vals=JSON.parse(x.value||'{}');host.querySelectorAll('[data-cfg]').forEach((el,i)=>{if(vals[i]!==undefined)el.value=vals[i]})}catch(e){}});
 const form=document.querySelector('#configModal form'); if(form) form.onsubmit=()=>{const vals={};host.querySelectorAll('[data-cfg]').forEach((el,i)=>vals[i]=el.value);box.value=JSON.stringify(vals)};
 document.querySelector('#configModal').classList.add('show')
}
function closeConfig(){document.querySelector('#configModal').classList.remove('show')}

function assetTab(name,btn){
 document.querySelectorAll('.asset-tab-panel').forEach(p=>p.classList.remove('active'));
 document.querySelectorAll('.asset-tabs button').forEach(b=>b.classList.remove('active'));
 const panel=document.querySelector('#asset-'+name); if(panel) panel.classList.add('active');
 if(btn) btn.classList.add('active');
 try{history.replaceState(null,'','#'+name)}catch(e){}
}
document.addEventListener('DOMContentLoaded',()=>{
 const name=(location.hash||'').replace('#','');
 if(['tech','service','faults','history','docs','links'].includes(name)){
  const buttons=[...document.querySelectorAll('.asset-tabs button')];
  const map={tech:0,service:1,faults:2,history:3,docs:4,links:5}; if(buttons[map[name]]) assetTab(name,buttons[map[name]]);
 }
});

function manageUser(u){
 const m=document.querySelector('#userManageModal'); if(!m)return;
 document.querySelector('#userEditForm').action='/user/'+u.id+'/update';
 document.querySelector('#editUserName').value=u.name||'';
 document.querySelector('#editUserEmail').value=u.email||'';
 document.querySelector('#editUserRole').value=u.role||'Viewer';
 document.querySelector('#editUserStatus').value=u.status||'Aktívny';
 document.querySelector('#editUserAvatar').textContent=(u.name||'U').split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase();
 document.querySelector('#editUserMeta').textContent=(u.email||'')+' · ID '+u.id;
 document.querySelector('#editUserLastLogin').textContent=u.last_login||'Zatiaľ bez prihlásenia';
 document.querySelector('#editUserState').textContent=u.status||'—';
 m.classList.add('show');
}
function closeUserManage(){document.querySelector('#userManageModal')?.classList.remove('show')}

async function checkSystemHealth(){
 const global=document.querySelector('#globalSystemStatus');
 const control=document.querySelector('#systemControlStatus');
 try{
  const started=performance.now();
  const res=await fetch('/api/health',{cache:'no-store',headers:{'Accept':'application/json'}});
  const data=await res.json();
  const browserMs=Math.round(performance.now()-started);
  const online=res.ok&&data.status==='online'&&data.database==='online'&&data.api==='online';
  const text=online?'● SYSTÉM ONLINE':'● SYSTÉM PROBLÉM';
  [global,control].forEach(el=>{if(el){el.textContent=text;el.classList.toggle('health-offline',!online);el.classList.toggle('health-online',online)}});
  const db=document.querySelector('#healthDb'),api=document.querySelector('#healthApi'),lat=document.querySelector('#healthLatency'),sys=document.querySelector('#healthSystem');
  if(db) db.innerHTML='<i>'+(data.database==='online'?'✓':'!')+'</i> Databáza <b>'+(data.database==='online'?'Online · '+(data.database_engine||'DB'):'Chyba')+'</b>';
  if(api) api.innerHTML='<i>'+(data.api==='online'?'✓':'!')+'</i> API server <b>'+(data.api==='online'?'Online':'Chyba')+'</b>';
  if(lat) lat.innerHTML='<i>↗</i> Odozva <b>'+browserMs+' ms</b>';
  if(sys) sys.innerHTML='<i>'+(online?'✓':'!')+'</i> Systém <b>'+(online?'Online':'Problém')+'</b>';
  const score=online?(browserMs<800?100:browserMs<2000?98:95):45;
  const scoreEl=document.querySelector('#healthScore'),grade=document.querySelector('#healthGrade');
  if(scoreEl)scoreEl.textContent=score;if(grade)grade.textContent=online?'A+':'!';
  const gauge=document.querySelector('#healthGauge');if(gauge)gauge.classList.toggle('health-offline',!online);
 }catch(e){
  [global,control].forEach(el=>{if(el){el.textContent='● SYSTÉM OFFLINE';el.classList.add('health-offline');el.classList.remove('health-online')}});
  const scoreEl=document.querySelector('#healthScore'),grade=document.querySelector('#healthGrade');
  if(scoreEl)scoreEl.textContent='0';if(grade)grade.textContent='!';
  const db=document.querySelector('#healthDb'),api=document.querySelector('#healthApi'),lat=document.querySelector('#healthLatency'),sys=document.querySelector('#healthSystem');
  if(db)db.innerHTML='<i>!</i> Databáza <b>Nedostupná</b>';
  if(api)api.innerHTML='<i>!</i> API server <b>Nedostupný</b>';
  if(lat)lat.innerHTML='<i>!</i> Odozva <b>Bez odpovede</b>';
  if(sys)sys.innerHTML='<i>!</i> Systém <b>Offline</b>';
  const gauge=document.querySelector('#healthGauge');if(gauge)gauge.classList.add('health-offline');
 }
}
function initHealthWatch(){
 let running=false;
 const tick=()=>{clearTimeout(window.GAMO_HEALTH_TIMER);window.GAMO_HEALTH_TIMER=setTimeout(async()=>{
  if(!document.hidden&&!running){running=true;try{await checkSystemHealth()}finally{running=false}}
  tick()
 },document.hidden?300000:120000)};
 checkSystemHealth().finally?.(()=>tick())||tick();
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkSystemHealth()});
 window.addEventListener('beforeunload',()=>clearTimeout(window.GAMO_HEALTH_TIMER));
}
document.addEventListener('DOMContentLoaded',initHealthWatch);

function buildingTab(name,btn){
 document.querySelectorAll('.building-tab-panel').forEach(p=>p.classList.remove('active'));
 document.querySelectorAll('.building-tabs button').forEach(b=>b.classList.remove('active'));
 const panel=document.querySelector('#building-'+name);if(panel)panel.classList.add('active');
 if(btn)btn.classList.add('active');
 try{history.replaceState(null,'','#'+name)}catch(e){}
}
function updateFacilityHealth(){
 const el=document.querySelector('#facilityHealth');if(!el)return;
 const open=Number(el.dataset.open||0),high=Number(el.dataset.high||0),overdue=Number(el.dataset.overdue||0),critical=Number(el.dataset.critical||0);
 let score=100-Math.min(35,high*12)-Math.min(20,Math.max(0,open-high)*4)-Math.min(20,overdue*5)-Math.min(10,critical*1.5);
 score=Math.max(0,Math.round(score*10)/10);
 const value=document.querySelector('#facilityHealthValue'),label=document.querySelector('#facilityHealthText');
 if(value)value.textContent=score.toFixed(1)+'%';
 let text='↑ stabilná prevádzka',state='good';
 if(high>0){text='! '+high+' závažné incidenty vyžadujú zásah';state='bad'}
 else if(open>0){text='• '+open+' otvorené incidenty';state='warn'}
 else if(overdue>0){text='• '+overdue+' servisné úlohy po termíne';state='warn'}
 if(label)label.textContent=text;
 el.classList.remove('facility-warn','facility-bad');if(state==='warn')el.classList.add('facility-warn');if(state==='bad')el.classList.add('facility-bad');
}
document.addEventListener('DOMContentLoaded',()=>{
 updateFacilityHealth();
 const n=(location.hash||'').replace('#','');
 if(['overview','spaces','technology','documents','twin'].includes(n)){
  const buttons=[...document.querySelectorAll('.building-tabs button')],map={overview:0,spaces:1,technology:2,documents:3,twin:4};
  if(buttons[map[n]])buildingTab(n,buttons[map[n]]);
 }
});

function initNotificationWatch(){
 let running=false;
 const tick=()=>{clearTimeout(window.GAMO_NOTIFICATION_TIMER);window.GAMO_NOTIFICATION_TIMER=setTimeout(async()=>{
  if(!document.hidden&&!running){running=true;try{await refreshNotifications(false)}finally{running=false}}
  refreshNotificationTimes();tick()
 },document.hidden?180000:60000)};
 refreshNotifications(false).finally(()=>tick());
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshNotifications(false)});
 window.addEventListener('beforeunload',()=>clearTimeout(window.GAMO_NOTIFICATION_TIMER));
}
document.addEventListener('DOMContentLoaded',()=>{initNotificationWatch();filterTicketAssets();initLiveTicket();initTicketInboxWatch();initDigitalTwinV2()});

function twinWorld(){return document.querySelector('.dt2-world')}
function twinApply(){
 const w=twinWorld();if(!w)return;
 const angle=parseFloat(w.dataset.angle||'-28'),tilt=Math.max(18,Math.min(76,parseFloat(w.dataset.tilt||'58'))),zoom=Math.max(.62,Math.min(1.7,parseFloat(w.dataset.zoom||'1')));
 w.dataset.angle=String(angle);w.dataset.tilt=String(tilt);w.dataset.zoom=String(zoom);
 w.style.setProperty('--dt2-angle',angle+'deg');w.style.setProperty('--dt2-tilt',tilt+'deg');w.style.setProperty('--dt2-zoom',zoom.toFixed(2));
 const needle=document.querySelector('.dt2-compass i');if(needle)needle.style.transform='rotate('+(-angle)+'deg)';
}
function twinRotate(delta){const w=twinWorld();if(!w)return;w.dataset.angle=String(parseFloat(w.dataset.angle||'-28')+delta);twinApply()}
function twinTilt(delta){const w=twinWorld();if(!w)return;w.dataset.tilt=String(parseFloat(w.dataset.tilt||'58')+delta);twinApply()}
function twinZoom(delta){const w=twinWorld();if(!w)return;w.dataset.zoom=String(parseFloat(w.dataset.zoom||'1')+delta);twinApply()}
function twinExplode(){
 const root=document.querySelector('#digitalTwinV2');if(!root)return;
 root.classList.toggle('exploded');
 const b=document.querySelector('#dt2ExplodeButton');if(b)b.classList.toggle('active',root.classList.contains('exploded'));
}
function twinFocusSelected(){
 const root=document.querySelector('#digitalTwinV2');if(!root)return;
 root.classList.toggle('focus-mode');
 document.querySelector('#dt2FocusButton')?.classList.toggle('active',root.classList.contains('focus-mode'));
}
function twinToggleTech(){
 const root=document.querySelector('#digitalTwinV2');if(!root)return;
 root.classList.toggle('tech-mode');
 document.querySelector('#dt2TechButton')?.classList.toggle('active',root.classList.contains('tech-mode'));
}

function twinReset(){
 const w=twinWorld(),root=document.querySelector('#digitalTwinV2');if(!w)return;
 w.dataset.angle='-28';w.dataset.tilt='58';w.dataset.zoom='1';root?.classList.remove('exploded','focus-mode','tech-mode');
 document.querySelector('#dt2ExplodeButton')?.classList.remove('active');document.querySelector('#dt2FocusButton')?.classList.remove('active');document.querySelector('#dt2TechButton')?.classList.remove('active');twinApply();
 const first=document.querySelector('[data-dt2-floor]');if(first)twinSelectFloor(first);
}
function twinPreset(name){
 const w=twinWorld();if(!w)return;
 const presets={iso:[-28,58,1],front:[0,73,.96],top:[-18,24,.92]};
 const p=presets[name]||presets.iso;w.dataset.angle=String(p[0]);w.dataset.tilt=String(p[1]);w.dataset.zoom=String(p[2]);twinApply();
}
function twinSelectFloor(el){
 if(!el)return;
 document.querySelectorAll('[data-dt2-floor]').forEach(x=>x.classList.toggle('selected',x===el));
 const id=String(el.dataset.floorId||'');
 const root=document.querySelector('#digitalTwinV2');if(root)root.dataset.selectedFloor=id;
 const open=document.querySelector('#dt2OpenFloorButton');if(open)open.disabled=!id;
 document.querySelectorAll('[data-dt2-list-floor]').forEach(x=>x.classList.toggle('selected',String(x.dataset.dt2ListFloor||'')===id));
 const values={dt2FloorCode:el.dataset.floorCode||'—',dt2FloorName:el.dataset.floorName||'—',dt2FloorRooms:el.dataset.floorRooms||'0',dt2FloorAssets:el.dataset.floorAssets||'0',dt2FloorArea:(el.dataset.floorArea||'0')+' m²',dt2FloorIncidents:el.dataset.floorIncidents||'0',dt2FloorFaults:el.dataset.floorFaults||'0',dt2FloorCritical:el.dataset.floorCritical||'0'};
 Object.entries(values).forEach(([id,value])=>{const n=document.getElementById(id);if(n)n.textContent=value});
 const box=document.querySelector('#dt2SelectedFloor');if(box)box.classList.toggle('has-alert',Number(el.dataset.floorIncidents||0)>0);
}
function twinSelectFloorById(id){
 const el=[...document.querySelectorAll('[data-dt2-floor]')].find(x=>String(x.dataset.floorId)===String(id));if(el)twinSelectFloor(el);
}
function twinOpenSelectedFloor(){
 const root=document.querySelector('#digitalTwinV2'),id=root?.dataset.selectedFloor;if(!id)return;
 const buttons=[...document.querySelectorAll('.building-tabs button')],spaces=buttons.find(b=>b.textContent.includes('Priestory'));
 if(spaces)buildingTab('spaces',spaces);
 setTimeout(()=>document.getElementById('floor-'+id)?.scrollIntoView({behavior:'smooth',block:'center'}),120);
}
function initDigitalTwinV2(){
 const stage=document.querySelector('#dt2Stage'),world=twinWorld();if(!stage||!world)return;
 twinApply();const first=document.querySelector('[data-dt2-floor]');if(first)twinSelectFloor(first);
 let drag=false,lastX=0,lastY=0,moved=false;
 stage.addEventListener('pointerdown',e=>{
  if(e.button!==0||e.target.closest('button'))return;
  drag=true;moved=false;lastX=e.clientX;lastY=e.clientY;stage.classList.add('dragging');stage.setPointerCapture?.(e.pointerId);
 });
 let twinFrame=0,pendingDx=0,pendingDy=0;
 stage.addEventListener('pointermove',e=>{
  if(!drag)return;const dx=e.clientX-lastX,dy=e.clientY-lastY;if(Math.abs(dx)+Math.abs(dy)>2)moved=true;
  lastX=e.clientX;lastY=e.clientY;pendingDx+=dx;pendingDy+=dy;
  if(twinFrame)return;
  twinFrame=requestAnimationFrame(()=>{
   twinFrame=0;
   world.dataset.angle=String(parseFloat(world.dataset.angle||'-28')+pendingDx*.28);
   world.dataset.tilt=String(parseFloat(world.dataset.tilt||'58')-pendingDy*.18);
   pendingDx=0;pendingDy=0;twinApply();
  });
 });
 const stop=e=>{if(!drag)return;drag=false;stage.classList.remove('dragging');try{stage.releasePointerCapture?.(e.pointerId)}catch(_){}};
 stage.addEventListener('pointerup',stop);stage.addEventListener('pointercancel',stop);
 stage.addEventListener('wheel',e=>{e.preventDefault();twinZoom(e.deltaY<0?.07:-.07)},{passive:false});
 stage.addEventListener('dblclick',e=>{if(!e.target.closest('button'))twinReset()});
 stage.addEventListener('keydown',e=>{
  if(e.key==='ArrowLeft'){e.preventDefault();twinRotate(-8)}
  else if(e.key==='ArrowRight'){e.preventDefault();twinRotate(8)}
  else if(e.key==='ArrowUp'){e.preventDefault();twinTilt(-5)}
  else if(e.key==='ArrowDown'){e.preventDefault();twinTilt(5)}
  else if(e.key==='+'||e.key==='='){e.preventDefault();twinZoom(.08)}
  else if(e.key==='-'){e.preventDefault();twinZoom(-.08)}
  else if(e.key==='0'){e.preventDefault();twinReset()}
 });
}
function filterCustomers(){
 const q=(document.querySelector('#customerSearch')?.value||'').trim().toLowerCase();
 const plan=document.querySelector('#customerPlanFilter')?.value||'';
 const status=document.querySelector('#customerStatusFilter')?.value||'';
 document.querySelectorAll('.customer-row').forEach(row=>{
  const text=row.dataset.search||'', rowPlan=row.dataset.plan||'', license=row.dataset.license||'', org=row.dataset.orgstatus||'', expired=row.dataset.expired==='1';
  const active=license==='Aktívna'&&org==='Aktívny'&&!expired;
  const matchText=!q||text.includes(q), matchPlan=!plan||rowPlan===plan, matchStatus=!status||(status==='active'?active:!active);
  row.style.display=(matchText&&matchPlan&&matchStatus)?'grid':'none';
 });
}
