from flask import Flask,render_template,request,redirect,url_for,jsonify,flash,session,abort
from sqlite3 import IntegrityError
import sqlite3, os, json, secrets, time
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date,timedelta,datetime
BASE=os.path.dirname(os.path.abspath(__file__))
if os.environ.get('GAMO_DESKTOP') == '1':
    DATA_DIR=os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'GAMO_FM', 'data')
else:
    DATA_DIR=os.environ.get('GAMO_DATA_DIR', os.path.join(BASE,'data'))
app=Flask(__name__)
app.secret_key=os.environ.get('GAMO_SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.environ.get('GAMO_HTTPS','0')=='1',PERMANENT_SESSION_LIFETIME=timedelta(hours=8),MAX_CONTENT_LENGTH=16*1024*1024)
DB=os.path.join(DATA_DIR,'gamo.db')
LOGIN_WINDOW=300
LOGIN_MAX_ATTEMPTS=6
_login_attempts={}
def audit(action,detail=''):
 try:
  x("insert into audit_log(user_id,user_name,action,detail,ip) values(?,?,?,?,?)",(session.get('user_id'),session.get('user_name','Systém'),action,detail,request.headers.get('X-Forwarded-For',request.remote_addr or '')))
 except Exception:
  pass
def con():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def q(sql,a=()):
 with con() as c:return c.execute(sql,a).fetchall()
def one(sql,a=()):
 with con() as c:return c.execute(sql,a).fetchone()
def x(sql,a=()):
 with con() as c:r=c.execute(sql,a);c.commit();return r.lastrowid
def init():
 os.makedirs(DATA_DIR,exist_ok=True)
 with con() as c:
  c.executescript("""CREATE TABLE IF NOT EXISTS buildings(id INTEGER PRIMARY KEY,code TEXT UNIQUE,name TEXT,address TEXT,manager TEXT,status TEXT DEFAULT 'Aktívna');CREATE TABLE IF NOT EXISTS floors(id INTEGER PRIMARY KEY,building_id INTEGER REFERENCES buildings(id) ON DELETE CASCADE,code TEXT,name TEXT);CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY,floor_id INTEGER REFERENCES floors(id) ON DELETE CASCADE,code TEXT,name TEXT,area REAL,tenant TEXT,zone TEXT);CREATE TABLE IF NOT EXISTS assets(id INTEGER PRIMARY KEY,asset_id TEXT UNIQUE,name TEXT,building_id INTEGER,floor_id INTEGER,room_id INTEGER,profession TEXT,grp TEXT,type TEXT,manufacturer TEXT,model TEXT,serial TEXT,system_id TEXT,parent_id INTEGER,status TEXT,criticality TEXT,service_months INTEGER,revision_months INTEGER,purchase_price REAL,installed TEXT,warranty TEXT,ip TEXT,protocol TEXT,notes TEXT);CREATE TABLE IF NOT EXISTS workorders(id INTEGER PRIMARY KEY,asset_id INTEGER,title TEXT,kind TEXT,priority TEXT,status TEXT,due TEXT,supplier TEXT,technician TEXT,cost REAL,description TEXT);CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY,asset_id INTEGER,title TEXT,severity TEXT,status TEXT,reported TEXT,impact TEXT,cause TEXT,cost REAL);CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT,role TEXT,status TEXT);CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT);""")
  cols=[r[1] for r in c.execute("pragma table_info(users)").fetchall()]
  if 'password_hash' not in cols: c.execute("alter table users add column password_hash TEXT")
  if 'last_login' not in cols: c.execute("alter table users add column last_login TEXT")
  c.execute("""CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY,created TEXT DEFAULT CURRENT_TIMESTAMP,user_id INTEGER,user_name TEXT,action TEXT,detail TEXT,ip TEXT);""")
  if not c.execute('select count(*) n from buildings').fetchone()['n']:
   c.execute("insert into buildings(code,name,address,manager) values('A','GAMO Centrum – Budova A','Kyjevské námestie 6, Banská Bystrica','Facility Management')"); c.execute("insert into buildings(code,name,address,manager) values('B','GAMO Centrum – Budova B','Banská Bystrica','Facility Management')")
   a=c.execute("select id from buildings where code='A'").fetchone()[0]; b=c.execute("select id from buildings where code='B'").fetchone()[0]
   f1=c.execute("insert into floors(building_id,code,name) values(?,?,?)",(a,'1.NP','Prízemie')).lastrowid; f2=c.execute("insert into floors(building_id,code,name) values(?,?,?)",(a,'2.NP','Administratíva')).lastrowid; fb=c.execute("insert into floors(building_id,code,name) values(?,?,?)",(b,'1.NP','Technické podlažie')).lastrowid
   r1=c.execute("insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",(f1,'A005','Kancelária',28.5,'GAMO','HVAC zóna 01')).lastrowid;r2=c.execute("insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",(f1,'A008','Kancelária',31.2,'GAMO','HVAC zóna 01')).lastrowid;r3=c.execute("insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",(f2,'A214','Serverovňa',18,'GAMO','IT kritická zóna')).lastrowid;r4=c.execute("insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",(fb,'B202','Technická miestnosť',42,'','HVAC zóna B')).lastrowid
   p=c.execute("insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,serial,system_id,status,criticality,service_months,revision_months,purchase_price,ip,protocol) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",('HVAC-000001','VRV vonkajšia jednotka',a,f1,r1,'HVAC','VRV systém','VRV-OUT','Daikin','RXYQ','SN240001','HVAC-A-VRV-01','Prevádzka','A',6,12,8900,'','Modbus')).lastrowid
   c.execute("insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,system_id,parent_id,status,criticality,purchase_price) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",('HVAC-000002','VRV vnútorná jednotka A005',a,f1,r1,'HVAC','VRV systém','VRV-IN','Daikin','FXZQ25','HVAC-A-VRV-01',p,'Prevádzka','B',1450));c.execute("insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,system_id,parent_id,status,criticality,purchase_price) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",('HVAC-000003','VRV vnútorná jednotka A008',a,f1,r2,'HVAC','VRV systém','VRV-IN','Daikin','FXZQ25','HVAC-A-VRV-01',p,'Prevádzka','B',1450));c.execute("insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,system_id,status,criticality,purchase_price,ip,protocol) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",('SLB-000001','Core switch serverovne',a,f2,r3,'SLB','LAN/WAN','Switch','Cisco','Catalyst','SLB-A-LAN-01','Prevádzka','A',3200,'10.0.1.2','SNMP'))
   c.execute("insert into workorders(asset_id,title,kind,priority,status,due,supplier,technician,cost,description) values(?,?,?,?,?,?,?,?,?,?)",(p,'Preventívny servis VRV','PM','Stredná','Plánované',str(date.today()+timedelta(days=12)),'Servis HVAC s.r.o.','Ján Technik',350,'Kontrola systému a filtrov'))
   c.execute("insert into incidents(asset_id,title,severity,status,reported,impact,cost) values(?,?,?,?,?,?,?)",(p,'Kolísanie tlaku VRV','Porucha','Otvorená',str(date.today()),'A005, A008 – znížený komfort',0))
   c.execute("insert into users(name,email,role,status,password_hash) values(?,?,?,?,?)",('GAMO Administrator','admin@gamo.sk','Administrator','Aktívny',generate_password_hash(os.environ.get('GAMO_ADMIN_PASSWORD','GamoFM2026!'))))
init()
with con() as c:
 c.execute("update users set password_hash=? where (password_hash is null or password_hash='') and lower(email)=?",(generate_password_hash(os.environ.get('GAMO_ADMIN_PASSWORD','GamoFM2026!')),'admin@gamo.sk')); c.commit()

@app.before_request
def require_login():
 if request.endpoint in ('login','static') or request.path.startswith('/static/'): return
 if not session.get('user_id'): return redirect(url_for('login',next=request.path))

@app.route('/login',methods=['GET','POST'])
def login():
 if session.get('user_id'): return redirect('/')
 error=None
 if request.method=='POST':
  email=(request.form.get('email') or '').strip().lower(); password=request.form.get('password') or ''
  key=(request.headers.get('X-Forwarded-For',request.remote_addr or '')+'|'+email)
  now=time.time(); attempts=[t for t in _login_attempts.get(key,[]) if now-t<LOGIN_WINDOW]
  if len(attempts)>=LOGIN_MAX_ATTEMPTS:
   return render_template('login.html',error='Príliš veľa neúspešných pokusov. Skús to znova o pár minút.'),429
  u=one('select * from users where lower(email)=?',(email,))
  if u and u['status']=='Aktívny' and u['password_hash'] and check_password_hash(u['password_hash'],password):
   _login_attempts.pop(key,None); session.clear(); session.permanent=True; session['user_id']=u['id']; session['user_name']=u['name']; session['user_role']=u['role']; session['csrf']=secrets.token_urlsafe(32)
   x("update users set last_login=datetime('now') where id=?",(u['id'],))
   return redirect(request.args.get('next') or '/')
  attempts.append(now); _login_attempts[key]=attempts; error='Nesprávny e-mail alebo heslo.'
 return render_template('login.html',error=error)

@app.get('/logout')
def logout():
 session.clear(); return redirect('/login')

@app.context_processor
def ctx(): return dict(today=date.today(),csrf_token=session.get('csrf',''),current_user={'name':session.get('user_name',''),'role':session.get('user_role','')})
@app.route('/')
def dashboard():
 s={'assets':one('select count(*) n from assets')['n'],'buildings':one('select count(*) n from buildings')['n'],'rooms':one('select count(*) n from rooms')['n'],'open':one("select count(*) n from incidents where status!='Ukončená'")['n'],'critical':one("select count(*) n from assets where criticality='A'")['n'],'orders':one("select count(*) n from workorders where status!='Ukončené'")['n']}
 return render_template('index.html',page='dashboard',s=s,buildings=q('select * from buildings'),recent=q('select w.*,a.asset_id,a.name asset from workorders w join assets a on a.id=w.asset_id order by w.id desc limit 6'),incidents=q('select i.*,a.asset_id from incidents i join assets a on a.id=i.asset_id order by i.id desc limit 5'))
@app.route('/buildings')
def buildings(): return render_template('index.html',page='buildings',buildings=q('select b.*,(select count(*) from floors where building_id=b.id) floors,(select count(*) from assets where building_id=b.id) assets from buildings b'))
@app.route('/building/<int:i>')
def building(i): return render_template('index.html',page='building',b=one('select * from buildings where id=?',(i,)),floors=q('select * from floors where building_id=?',(i,)),rooms=q('select r.*,f.code floor from rooms r join floors f on f.id=r.floor_id where f.building_id=?',(i,)),assets=q('select a.*,r.code room from assets a left join rooms r on r.id=a.room_id where a.building_id=?',(i,)))
@app.route('/assets')
def assets(): return render_template('index.html',page='assets',assets=q('select a.*,b.code building,r.code room from assets a left join buildings b on b.id=a.building_id left join rooms r on r.id=a.room_id order by a.asset_id'))
@app.route('/asset/<int:i>')
def asset(i): return render_template('index.html',page='asset',a=one('select a.*,b.name building,f.code floor,r.code room,r.name room_name,r.area from assets a left join buildings b on b.id=a.building_id left join floors f on f.id=a.floor_id left join rooms r on r.id=a.room_id where a.id=?',(i,)),children=q('select * from assets where parent_id=?',(i,)),orders=q('select * from workorders where asset_id=? order by id desc',(i,)),incidents=q('select * from incidents where asset_id=? order by id desc',(i,)))
@app.route('/maintenance')
def maintenance(): return render_template('index.html',page='maintenance',orders=q('select w.*,a.asset_id,a.name asset from workorders w join assets a on a.id=w.asset_id order by w.id desc'))
@app.route('/incidents')
def incidents(): return render_template('index.html',page='incidents',incidents=q('select i.*,a.asset_id,a.name asset from incidents i join assets a on a.id=i.asset_id order by i.id desc'))
@app.route('/admin')
def admin(): return render_template('index.html',page='admin',users=q('select * from users'),buildings=q('select * from buildings'),audit_rows=q('select * from audit_log order by id desc limit 20'))
@app.post('/add/<what>')
def add(what):
 f=request.form
 try:
  if what=='building':
   code=f.get('code','').strip().upper(); name=f.get('name','').strip()
   if not code or not name: flash('Kód a názov budovy sú povinné.','error')
   elif one('select id from buildings where upper(code)=?',(code,)): flash(f'Budova s kódom {code} už existuje.','error')
   else: x('insert into buildings(code,name,address,manager) values(?,?,?,?)',(code,name,f.get('address','').strip(),f.get('manager','').strip())); flash('Budova bola vytvorená.','success')
  elif what=='floor': x('insert into floors(building_id,code,name) values(?,?,?)',(f['building_id'],f['code'].strip(),f['name'].strip())); flash('Podlažie bolo pridané.','success')
  elif what=='room': x('insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)',(f['floor_id'],f['code'].strip(),f['name'].strip(),f.get('area') or 0,f.get('tenant','').strip(),f.get('zone','').strip())); flash('Miestnosť bola pridaná.','success')
  elif what=='asset':
   aid=f.get('asset_id','').strip().upper()
   if one('select id from assets where upper(asset_id)=?',(aid,)): flash(f'Asset ID {aid} už existuje.','error')
   else: x('insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,serial,system_id,parent_id,status,criticality,service_months,revision_months,purchase_price,ip,protocol,notes) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',tuple((aid if k=='asset_id' else f.get(k)) or None for k in ['asset_id','name','building_id','floor_id','room_id','profession','grp','type','manufacturer','model','serial','system_id','parent_id','status','criticality','service_months','revision_months','purchase_price','ip','protocol','notes'])); flash('Asset bol vytvorený.','success')
  elif what=='workorder':
   allowed_priority={'Nízka','Stredná','Vysoká','Kritická'}; allowed_status={'Plánované','Pridelené','Prebieha','Pozastavené','Ukončené','Zrušené'}; allowed_kind={'PM','REV','OPR','VYM'}
   if f.get('priority') not in allowed_priority or f.get('status') not in allowed_status or f.get('kind') not in allowed_kind: raise ValueError()
   x('insert into workorders(asset_id,title,kind,priority,status,due,supplier,technician,cost,description) values(?,?,?,?,?,?,?,?,?,?)',tuple(f.get(k,'') for k in ['asset_id','title','kind','priority','status','due','supplier','technician','cost','description'])); audit('WORKORDER_CREATE',f.get('title','')); flash('Pracovný príkaz bol vytvorený.','success')
  elif what=='incident':
   allowed_severity={'Nízka','Stredná','Vysoká','Kritická','Havária'}; allowed_status={'Otvorená','Pridelená','Rieši sa','Čaká na diel','Vyriešená','Ukončená'}
   if f.get('severity') not in allowed_severity or f.get('status') not in allowed_status: raise ValueError()
   x('insert into incidents(asset_id,title,severity,status,reported,impact,cause,cost) values(?,?,?,?,?,?,?,?)',tuple(f.get(k,'') for k in ['asset_id','title','severity','status','reported','impact','cause','cost'])); audit('INCIDENT_CREATE',f.get('title','')); flash('Incident bol zaevidovaný.','success')
  elif what=='user':
   pwd=f.get('password') or 'GamoFM2026!'
   x('insert into users(name,email,role,status,password_hash) values(?,?,?,?,?)',(f['name'],f['email'].strip().lower(),f['role'],f['status'],generate_password_hash(pwd))); flash('Používateľ bol vytvorený.','success')
 except (IntegrityError,ValueError):
  flash('Záznam sa nepodarilo uložiť. Skontroluj duplicity a zadané hodnoty.','error')
 except Exception:
  flash('Pri ukladaní nastala chyba. Dáta neboli poškodené.','error')
 return redirect(request.referrer or '/')
@app.post('/user/<int:i>/update')
def update_user(i):
 f=request.form
 u=one('select * from users where id=?',(i,))
 if not u:
  abort(404)
 name=(f.get('name') or '').strip(); email=(f.get('email') or '').strip().lower()
 role=f.get('role') or 'Viewer'; status=f.get('status') or 'Aktívny'; pwd=f.get('password') or ''
 allowed_roles={'Administrator','Facility Manager','Technik','Servisný technik','Viewer'}
 if not name or not email or role not in allowed_roles or status not in {'Aktívny','Neaktívny'}:
  flash('Skontroluj údaje používateľa.','error'); return redirect('/admin#usersAdmin')
 if i==session.get('user_id') and status!='Aktívny':
  flash('Aktuálne prihlásený účet nie je možné deaktivovať.','error'); return redirect('/admin#usersAdmin')
 try:
  duplicate=one('select id from users where lower(email)=? and id<>?',(email,i))
  if duplicate: raise IntegrityError()
  if pwd:
   x('update users set name=?,email=?,role=?,status=?,password_hash=? where id=?',(name,email,role,status,generate_password_hash(pwd),i))
  else:
   x('update users set name=?,email=?,role=?,status=? where id=?',(name,email,role,status,i))
  if i==session.get('user_id'):
   session['user_name']=name; session['user_role']=role
  audit('USER_UPDATE',f'{name} · {role} · {status}')
  flash('Používateľ bol úspešne upravený.','success')
 except IntegrityError:
  flash('Tento e-mail už používa iný účet.','error')
 return redirect('/admin#usersAdmin')

@app.post('/delete/<what>/<int:i>')
def delete(what,i):
 table={'building':'buildings','floor':'floors','room':'rooms','asset':'assets','workorder':'workorders','incident':'incidents','user':'users'}[what]; x(f'delete from {table} where id=?',(i,)); return redirect(request.referrer or '/')
@app.post('/status/<what>/<int:i>')
def status(what,i):
 table={'asset':'assets','workorder':'workorders','incident':'incidents'}[what]; x(f'update {table} set status=? where id=?',(request.form['status'],i)); return redirect(request.referrer or '/')
@app.route('/api/floors/<int:b>')
def api_floors(b): return jsonify([dict(r) for r in q('select * from floors where building_id=?',(b,))])
@app.route('/api/rooms/<int:f>')
def api_rooms(f): return jsonify([dict(r) for r in q('select * from rooms where floor_id=?',(f,))])
@app.get('/api/search')
def api_search():
 term=(request.args.get('q') or '').strip()
 if len(term)<2:return jsonify([])
 like=f'%{term}%'; out=[]
 for r in q('select id,asset_id,name,profession from assets where asset_id like ? or name like ? or manufacturer like ? limit 8',(like,like,like)):
  out.append({'kind':'Asset','title':f"{r['asset_id']} · {r['name']}",'subtitle':r['profession'] or '','url':f"/asset/{r['id']}"})
 for r in q('select id,code,name,address from buildings where code like ? or name like ? or address like ? limit 5',(like,like,like)):
  out.append({'kind':'Budova','title':f"{r['code']} · {r['name']}",'subtitle':r['address'] or '','url':f"/building/{r['id']}"})
 return jsonify(out[:12])
@app.get('/api/health')
def api_health():
 started=time.time()
 db_ok=False; db_ms=None; counts={}
 try:
  t=time.time()
  row=one('select 1 as ok')
  db_ms=round((time.time()-t)*1000,1)
  db_ok=bool(row and row['ok']==1)
  if db_ok:
   counts={'buildings':one('select count(*) n from buildings')['n'],'assets':one('select count(*) n from assets')['n']}
 except Exception:
  db_ok=False
 ok=db_ok
 return jsonify({
  'status':'online' if ok else 'degraded',
  'database':'online' if db_ok else 'offline',
  'api':'online',
  'database_ms':db_ms,
  'response_ms':round((time.time()-started)*1000,1),
  'version':'9.0.0.4',
  'counts':counts,
  'checked_at':datetime.now().isoformat(timespec='seconds')
 }), (200 if ok else 503)

@app.get('/api/notifications')
def api_notifications():
 out=[]
 for r in q("select i.id,i.title,i.status,a.id aid,a.asset_id from incidents i join assets a on a.id=i.asset_id where i.status!='Ukončená' order by i.id desc limit 6"):
  out.append({'title':r['title'],'subtitle':r['asset_id'],'status':r['status'],'level':'red','url':f"/asset/{r['aid']}"})
 for r in q("select w.id,w.title,w.status,w.due,a.id aid,a.asset_id from workorders w join assets a on a.id=w.asset_id where w.status!='Ukončené' order by w.due limit 6"):
  out.append({'title':r['title'],'subtitle':f"{r['asset_id']} · termín {r['due'] or '—'}",'status':r['status'],'level':'blue','url':f"/asset/{r['aid']}"})
 return jsonify(out[:10])
@app.get('/api/setting')
def api_setting():
 section=request.args.get('section',''); r=one('select v from settings where k=?',(section,)); return jsonify({'value':r['v'] if r else ''})
@app.post('/settings/save')
def save_setting():
 section=(request.form.get('section') or '').strip(); value=(request.form.get('value') or '').strip()
 if not section: flash('Chýba názov konfiguračnej sekcie.','error')
 else:
  x('insert into settings(k,v) values(?,?) on conflict(k) do update set v=excluded.v',(section,value)); flash(f'Konfigurácia „{section}“ bola uložená.','success')
 return redirect('/admin')

if __name__=='__main__': app.run(debug=False,port=5050)
