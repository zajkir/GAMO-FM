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
function filterRows(){let v=document.querySelector('#search').value.toLowerCase();document.querySelectorAll('#assettable tr').forEach((r,i)=>{if(i)r.style.display=r.innerText.toLowerCase().includes(v)?'':'none'})}
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
 if(list)list.innerHTML=items.length?items.map(x=>{const seen=read.has(x.key);return `<a class="searchitem notification-item ${seen?'notification-read':'notification-new'}" href="${x.url}"><div class="notification-copy"><b>${x.title}</b><small>${x.subtitle}</small><time data-notification-time="${x.created_at||''}">${notificationTime(x.created_at)}</time></div><span class="badge ${x.level||''}">${x.status}</span></a>`}).join(''):'<div class="empty">Žiadne aktívne upozornenia.</div>';
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
let searchTimer;function globalSearch(v){clearTimeout(searchTimer);let box=document.querySelector('#globalSearchResults');if(v.trim().length<2){box.innerHTML='<div class="empty">Začni písať aspoň 2 znaky.</div>';return}searchTimer=setTimeout(()=>fetch('/api/search?q='+encodeURIComponent(v)).then(r=>r.json()).then(items=>{box.innerHTML=items.length?items.map(x=>`<a class="searchitem" href="${x.url}"><b>${x.title}</b><small>${x.subtitle}</small><span>${x.kind}</span></a>`).join(''):'<div class="empty">Nenašli sa žiadne výsledky.</div>'}),180)}
const configSchemas={
'Organizačná štruktúra':{icon:'▦',group:'FACILITY STRUCTURE',fields:[['Predvolený názov organizácie',APP_BRAND,'text'],['Kód lokality',APP_ORG_CODE,'text'],['Číslovanie podlaží','NP / PP','select',['NP / PP','Číselné','Vlastné']],['Prevádzkové zóny','Zapnuté','select',['Zapnuté','Vypnuté']]]},
'Technológie & číselníky':{icon:'◇',group:'ASSET DICTIONARIES',fields:[['Predvolená profesia','HVAC','text'],['Stav nového assetu','Prevádzka','select',['Prevádzka','Servis','Mimo prevádzky']],['Kritickosť','B','select',['A','B','C']],['Výrobcovia','Spravované číselníkom','text']]},
'Asset ID generátor':{icon:'#',group:'ASSET IDENTIFICATION',fields:[['Maska Asset ID','{PROF}-000001','text'],['Počiatočné číslo','1','number'],['Dĺžka poradového čísla','6','number'],['Automatické generovanie','Zapnuté','select',['Zapnuté','Vypnuté']]]},
'Servis & SLA':{icon:'◷',group:'SERVICE POLICY',fields:[['Predvolený PM interval (mesiace)','6','number'],['Revízny interval (mesiace)','12','number'],['Predvolená priorita','Stredná','select',['Nízka','Stredná','Vysoká','Kritická']],['SLA eskalácia','24 h','text']]},
'Notifikačné centrum':{icon:'◉',group:'NOTIFICATIONS',fields:[['Upozorniť pred termínom','14 dní','text'],['Kritické incidenty','Okamžite','select',['Okamžite','Každú hodinu','Denne']],['E-mailové notifikácie','Zapnuté','select',['Zapnuté','Vypnuté']],['Systémové upozornenia','Zapnuté','select',['Zapnuté','Vypnuté']]]},
'Role & bezpečnosť':{icon:'⌾',group:'ACCESS CONTROL',fields:[['Predvolená rola','Viewer','select',['Administrator','Facility Manager','Technik','Servisný technik','Viewer']],['Audit zmien','Zapnutý','select',['Zapnutý','Vypnutý']],['Vynútiť silné heslá','Áno','select',['Áno','Nie']],['Neaktívny účet','Blokovať prihlásenie','text']]},
'Import / Export':{icon:'⇩',group:'DATA MANAGEMENT',fields:[['Formát exportu','CSV','select',['CSV','XLSX','JSON']],['Kódovanie','UTF-8','text'],['Import duplicít','Preskočiť','select',['Preskočiť','Aktualizovať','Zastaviť']],['Audit importu','Zapnutý','select',['Zapnutý','Vypnutý']]]},
'Dokumentácia':{icon:'▤',group:'DOCUMENT CONTROL',fields:[['Kategórie','Technická / Revízna / Servisná','text'],['Povolené prílohy','PDF, DOCX, XLSX, JPG, PNG','text'],['Verzovanie','Zapnuté','select',['Zapnuté','Vypnuté']],['Povinný popis','Áno','select',['Áno','Nie']]]},
'Zálohovanie':{icon:'▣',group:'BACKUP POLICY',fields:[['Automatické zálohy','Denne','select',['Denne','Týždenne','Manuálne']],['Čas zálohy','02:00','time'],['Retencia','30 dní','text'],['Kontrola integrity','Zapnutá','select',['Zapnutá','Vypnutá']]]},
'Aktualizácie':{icon:'↻',group:'UPDATE CHANNEL',fields:[['Kanál','Stable','select',['Stable','Preview','Manuálny']],['Automatická kontrola','Zapnutá','select',['Zapnutá','Vypnutá']],['Aktuálna verzia','9.0.0.5','text'],['Inštalácia','Po potvrdení','select',['Po potvrdení','Automaticky']]]},
'Relácie':{icon:'⌁',group:'SESSION SECURITY',fields:[['Čas relácie','8 hodín','text'],['Remember me','Povolené','select',['Povolené','Zakázané']],['Opätovné overenie admina','30 min','text'],['Odhlásiť pri neaktivite','Áno','select',['Áno','Nie']]]},
'Prevádzka systému':{icon:'⚙',group:'SYSTEM RUNTIME',fields:[['Režim','Produkcia','select',['Produkcia','Údržba']],['Časové pásmo','Europe/Bratislava','text'],['Logovanie','Štandardné','select',['Minimálne','Štandardné','Detailné']],['Health monitoring','Zapnutý','select',['Zapnutý','Vypnutý']]]}
};
function configModal(title,desc){
 const schema=configSchemas[title]||{icon:'⚙',group:'SYSTEM CONFIGURATION',fields:[['Hodnota','','text']]};
 document.querySelector('#configTitle').textContent=title;document.querySelector('#configDesc').textContent=desc;
 document.querySelector('#configSection').value=title;
 const box=document.querySelector('#configValue'); box.style.display='none';
 let host=document.querySelector('#configFields');
 if(!host){host=document.createElement('div');host.id='configFields';box.parentNode.insertBefore(host,box)}
 host.innerHTML='<div class="config-modal-hero"><span>'+schema.icon+'</span><div><small>'+schema.group+'</small><b>'+title+'</b><p>'+desc+'</p></div></div><div class="config-field-grid">'+schema.fields.map((f,i)=>{let input=f[2]==='select'?'<select data-cfg="'+i+'">'+f[3].map(x=>'<option>'+x+'</option>').join('')+'</select>':'<input data-cfg="'+i+'" type="'+f[2]+'" value="'+f[1]+'">';return '<label><span>'+f[0]+'</span>'+input+'<small>'+(i===0?'Hlavné nastavenie tejto oblasti':'Upraviteľný systémový parameter')+'</small></label>'}).join('')+'</div>';
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
document.addEventListener('DOMContentLoaded',()=>{checkSystemHealth();setInterval(checkSystemHealth,30000)});

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

document.addEventListener('DOMContentLoaded',()=>{refreshNotifications(false);setInterval(()=>refreshNotifications(false),15000);setInterval(refreshNotificationTimes,30000);const thread=document.querySelector('#ticketThread');if(thread)thread.scrollTop=thread.scrollHeight});

function twinApply(){const s=document.querySelector('.twin-stack');if(!s)return;s.style.setProperty('--twin-angle',(s.dataset.angle||'-18')+'deg');s.style.setProperty('--twin-tilt',(s.dataset.tilt||'58')+'deg');s.style.setProperty('--twin-zoom',s.dataset.zoom||'1')}
function twinRotate(delta){const s=document.querySelector('.twin-stack');if(!s)return;s.dataset.angle=parseFloat(s.dataset.angle||'-18')+delta;twinApply()}
function twinTilt(delta){const s=document.querySelector('.twin-stack');if(!s)return;s.dataset.tilt=Math.max(18,Math.min(68,parseFloat(s.dataset.tilt||'58')+delta));twinApply()}
function twinZoom(delta){const s=document.querySelector('.twin-stack');if(!s)return;s.dataset.zoom=Math.max(.7,Math.min(1.8,parseFloat(s.dataset.zoom||'1')+delta)).toFixed(2);twinApply()}
function twinExplode(){const s=document.querySelector('.twin-stack');if(!s)return;s.classList.toggle('exploded')}
function twinReset(){const s=document.querySelector('.twin-stack');if(!s)return;s.dataset.angle='-18';s.dataset.tilt='58';s.dataset.zoom='1.12';s.classList.remove('exploded');twinApply()}
document.addEventListener('wheel',e=>{const scene=e.target.closest&&e.target.closest('.twin-scene');if(!scene)return;e.preventDefault();twinZoom(e.deltaY<0?.08:-.08)},{passive:false});

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
