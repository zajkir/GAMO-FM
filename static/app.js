const defs={
building:[['code','Kód','A'],['name','Názov budovy',''],['address','Adresa',''],['manager','Správca','Facility Management']],
floor:[['building_id','ID budovy','1'],['code','Kód podlažia','1.NP'],['name','Názov','Prízemie']],
room:[['floor_id','ID podlažia','1'],['code','Kód miestnosti','A101'],['name','Názov','Kancelária'],['area','Plocha m²','25'],['tenant','Nájomca','GAMO'],['zone','Zóna','']],
asset:[['asset_id','Asset ID','HVAC-000010'],['name','Názov zariadenia',''],['building_id','ID budovy','1'],['floor_id','ID podlažia','1'],['room_id','ID miestnosti','1'],['profession','Profesia','HVAC'],['grp','Skupina','VRV systém'],['type','Typ','VRV-IN'],['manufacturer','Výrobca',''],['model','Model',''],['serial','Výrobné číslo',''],['system_id','System ID',''],['parent_id','Parent Asset ID',''],{name:'status',label:'Stav',type:'select',options:['Prevádzka','Mimo prevádzky','Servis','Porucha','Vyradené'],value:'Prevádzka'},{name:'criticality',label:'Kritickosť',type:'select',options:['A','B','C'],value:'B'},['service_months','Servis interval mes.','6'],['revision_months','Revízia interval mes.','12'],['purchase_price','Cena €','0'],['ip','IP adresa',''],['protocol','Protokol',''],['notes','Poznámka','']],
workorder:[['asset_id','Asset DB ID',currentAsset||'1'],{name:'title',label:'Názov pracovného príkazu',type:'select',options:['Preventívna údržba','Pravidelná revízia','Oprava poruchy','Havarijný zásah','Výmena zariadenia','Diagnostika','Kontrola zariadenia'],value:'Preventívna údržba'},{name:'kind',label:'Typ zásahu',type:'select',options:['PM','REV','OPR','VYM'],value:'PM'},{name:'priority',label:'Priorita',type:'select',options:['Nízka','Stredná','Vysoká','Kritická'],value:'Stredná'},{name:'status',label:'Stav',type:'select',options:['Plánované','Pridelené','Prebieha','Pozastavené','Ukončené','Zrušené'],value:'Plánované'},['due','Termín',''],['supplier','Dodávateľ',''],['technician','Technik',''],['cost','Náklad €','0'],['description','Popis','']],
incident:[['asset_id','Asset DB ID',currentAsset||'1'],['title','Názov incidentu',''],{name:'severity',label:'Závažnosť',type:'select',options:['Nízka','Stredná','Vysoká','Kritická','Havária'],value:'Stredná'},{name:'status',label:'Stav',type:'select',options:['Otvorená','Pridelená','Rieši sa','Čaká na diel','Vyriešená','Ukončená'],value:'Otvorená'},['reported','Nahlásené',''],['impact','Dopad',''],['cause','Príčina',''],['cost','Náklad €','0']],
user:[['name','Meno',''],['email','E-mail',''],{name:'role',label:'Rola',type:'select',options:['Administrator','Facility Manager','Technik','Servisný technik','Viewer'],value:'Technik'},{name:'status',label:'Stav používateľa',type:'select',options:['Aktívny','Neaktívny'],value:'Aktívny'},['password','Dočasné heslo','']]
};
function fieldDef(a){return Array.isArray(a)?{name:a[0],label:a[1],value:a[2],type:(a[0]=='password'?'password':'text')} : a}
function modal(t){let f=defs[t],h='<div class="formgrid">';f.forEach((raw,i)=>{const a=fieldDef(raw),full=['notes','description','impact','cause'].includes(a.name)?'full':'';let control;if(a.type==='select'){control=`<select name="${a.name}" ${i<2?'required':''}>${a.options.map(o=>`<option value="${o}" ${o===a.value?'selected':''}>${o}</option>`).join('')}</select>`}else{control=`<input type="${a.type||'text'}" name="${a.name}" value="${a.value||''}" ${i<2?'required':''}>`}h+=`<div class="field ${full}"><label>${a.label}</label>${control}</div>`});h+='</div>';document.querySelector('#fields').innerHTML=h;document.querySelector('#mform').action='/add/'+t;const titles={user:'Nový používateľ',incident:'Nahlásiť nový incident',workorder:'Nový pracovný príkaz',asset:'Nový asset',building:'Nová budova',floor:'Nové podlažie',room:'Nová miestnosť'};document.querySelector('#mtitle').textContent=titles[t]||'Nový záznam';document.querySelector('#modal').classList.add('show')}
function closeM(){document.querySelector('#modal').classList.remove('show')}function filterRows(){let v=document.querySelector('#search').value.toLowerCase();document.querySelectorAll('#assettable tr').forEach((r,i)=>{if(i)r.style.display=r.innerText.toLowerCase().includes(v)?'':'none'})}
function toggleQuickSearch(){document.querySelector('#quickSearch').classList.toggle('showpanel');setTimeout(()=>document.querySelector('#globalSearchInput')?.focus(),50)}
function toggleNotifications(){let p=document.querySelector('#notifications');p.classList.toggle('showpanel');if(p.classList.contains('showpanel'))fetch('/api/notifications').then(r=>r.json()).then(items=>{document.querySelector('#notificationList').innerHTML=items.length?items.map(x=>`<a class="searchitem" href="${x.url}"><b>${x.title}</b><small>${x.subtitle}</small><span class="badge ${x.level||''}">${x.status}</span></a>`).join(''):'<div class="empty">Žiadne aktívne upozornenia.</div>'}).catch(()=>document.querySelector('#notificationList').innerHTML='<div class="empty">Notifikácie sa nepodarilo načítať.</div>')}
let searchTimer;function globalSearch(v){clearTimeout(searchTimer);let box=document.querySelector('#globalSearchResults');if(v.trim().length<2){box.innerHTML='<div class="empty">Začni písať aspoň 2 znaky.</div>';return}searchTimer=setTimeout(()=>fetch('/api/search?q='+encodeURIComponent(v)).then(r=>r.json()).then(items=>{box.innerHTML=items.length?items.map(x=>`<a class="searchitem" href="${x.url}"><b>${x.title}</b><small>${x.subtitle}</small><span>${x.kind}</span></a>`).join(''):'<div class="empty">Nenašli sa žiadne výsledky.</div>'}),180)}
const configSchemas={
'Organizačná štruktúra':{icon:'▦',group:'FACILITY STRUCTURE',fields:[['Predvolený názov organizácie','GAMO a.s.','text'],['Kód lokality','GAMO','text'],['Číslovanie podlaží','NP / PP','select',['NP / PP','Číselné','Vlastné']],['Prevádzkové zóny','Zapnuté','select',['Zapnuté','Vypnuté']]]},
'Technológie & číselníky':{icon:'◇',group:'ASSET DICTIONARIES',fields:[['Predvolená profesia','HVAC','text'],['Stav nového assetu','Prevádzka','select',['Prevádzka','Servis','Mimo prevádzky']],['Kritickosť','B','select',['A','B','C']],['Výrobcovia','Spravované číselníkom','text']]},
'Asset ID generátor':{icon:'#',group:'ASSET IDENTIFICATION',fields:[['Maska Asset ID','{PROF}-000001','text'],['Počiatočné číslo','1','number'],['Dĺžka poradového čísla','6','number'],['Automatické generovanie','Zapnuté','select',['Zapnuté','Vypnuté']]]},
'Servis & SLA':{icon:'◷',group:'SERVICE POLICY',fields:[['Predvolený PM interval (mesiace)','6','number'],['Revízny interval (mesiace)','12','number'],['Predvolená priorita','Stredná','select',['Nízka','Stredná','Vysoká','Kritická']],['SLA eskalácia','24 h','text']]},
'Notifikačné centrum':{icon:'◉',group:'NOTIFICATIONS',fields:[['Upozorniť pred termínom','14 dní','text'],['Kritické incidenty','Okamžite','select',['Okamžite','Každú hodinu','Denne']],['E-mailové notifikácie','Zapnuté','select',['Zapnuté','Vypnuté']],['Systémové upozornenia','Zapnuté','select',['Zapnuté','Vypnuté']]]},
'Role & bezpečnosť':{icon:'⌾',group:'ACCESS CONTROL',fields:[['Predvolená rola','Viewer','select',['Administrator','Facility Manager','Technik','Servisný technik','Viewer']],['Audit zmien','Zapnutý','select',['Zapnutý','Vypnutý']],['Vynútiť silné heslá','Áno','select',['Áno','Nie']],['Neaktívny účet','Blokovať prihlásenie','text']]},
'Import / Export':{icon:'⇩',group:'DATA MANAGEMENT',fields:[['Formát exportu','CSV','select',['CSV','XLSX','JSON']],['Kódovanie','UTF-8','text'],['Import duplicít','Preskočiť','select',['Preskočiť','Aktualizovať','Zastaviť']],['Audit importu','Zapnutý','select',['Zapnutý','Vypnutý']]]},
'Dokumentácia':{icon:'▤',group:'DOCUMENT CONTROL',fields:[['Kategórie','Technická / Revízna / Servisná','text'],['Povolené prílohy','PDF, DOCX, XLSX, JPG, PNG','text'],['Verzovanie','Zapnuté','select',['Zapnuté','Vypnuté']],['Povinný popis','Áno','select',['Áno','Nie']]]},
'Zálohovanie':{icon:'▣',group:'BACKUP POLICY',fields:[['Automatické zálohy','Denne','select',['Denne','Týždenne','Manuálne']],['Čas zálohy','02:00','time'],['Retencia','30 dní','text'],['Kontrola integrity','Zapnutá','select',['Zapnutá','Vypnutá']]]},
'Aktualizácie':{icon:'↻',group:'UPDATE CHANNEL',fields:[['Kanál','Stable','select',['Stable','Preview','Manuálny']],['Automatická kontrola','Zapnutá','select',['Zapnutá','Vypnutá']],['Aktuálna verzia','9.0.0.4','text'],['Inštalácia','Po potvrdení','select',['Po potvrdení','Automaticky']]]},
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
 if(['tech','service','faults','docs','links'].includes(name)){
  const buttons=[...document.querySelectorAll('.asset-tabs button')];
  const map={tech:0,service:1,faults:2,docs:3,links:4}; if(buttons[map[name]]) assetTab(name,buttons[map[name]]);
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
