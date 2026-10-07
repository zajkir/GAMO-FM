from flask import Flask,render_template,request,redirect,url_for,jsonify,flash,session,abort,send_file,has_request_context
from sqlite3 import IntegrityError
import sqlite3, os, json, secrets, time, io, zipfile
try:
 import psycopg
 from psycopg.rows import dict_row
except ImportError:
 psycopg=None; dict_row=None
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date,timedelta,datetime
from db_migrations import run_migrations
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
BASE=os.path.dirname(os.path.abspath(__file__))
if os.environ.get('GAMO_DESKTOP') == '1':
    DATA_DIR=os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'GAMO_FM', 'data')
else:
    DATA_DIR=os.environ.get('GAMO_DATA_DIR', os.path.join(BASE,'data'))
app=Flask(__name__)
app.secret_key=os.environ.get('GAMO_SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.environ.get('GAMO_HTTPS','1' if os.environ.get('DATABASE_URL') else '0')=='1',PERMANENT_SESSION_LIFETIME=timedelta(days=30),MAX_CONTENT_LENGTH=16*1024*1024)
DB=os.path.join(DATA_DIR,'gamo.db')
LOGIN_WINDOW=300
LOGIN_MAX_ATTEMPTS=6
_login_attempts={}
ROLE_PERMISSIONS={
 'Administrator':{'view','facility_write','asset_write','maintenance_write','incident_write','documents_write','users_manage','settings_manage','audit_view','platform_manage','reports_view'},
 'Facility Manager':{'view','facility_write','asset_write','maintenance_write','incident_write','documents_write','reports_view'},
 'Technik':{'view','maintenance_write','incident_write'},
 'Servisný technik':{'view','maintenance_write','incident_write'},
 'Viewer':{'view'}
}
PLAN_LIMITS={
 'BASIC':{'users':5,'buildings':2,'assets':500},
 'BUSINESS':{'users':25,'buildings':10,'assets':5000},
 'ENTERPRISE':{'users':None,'buildings':None,'assets':None},
 'INTERNAL':{'users':None,'buildings':None,'assets':None}
}

def can(permission):
 return permission in ROLE_PERMISSIONS.get(session.get('user_role','Viewer'),{'view'})

def actor_org_id():
 return session.get('organization_id')

def org_id():
 return session.get('support_target_org_id') or actor_org_id()

def support_mode():
 return bool(session.get('support_target_org_id'))

def is_gamo_admin():
 return bool(not support_mode() and actor_org_id() and session.get('organization_code')=='GAMO' and session.get('user_role')=='Administrator')

def owns_building(building_id):
 oid=org_id()
 return bool(oid and one('select id from buildings where id=? and organization_id=?',(building_id,oid)))

def owns_asset(asset_id):
 oid=org_id()
 return bool(oid and one('select a.id from assets a join buildings b on b.id=a.building_id where a.id=? and b.organization_id=?',(asset_id,oid)))

def owns_floor(floor_id):
 return bool(org_id() and one('select f.id from floors f join buildings b on b.id=f.building_id where f.id=? and b.organization_id=?',(floor_id,org_id())))

def owns_room(room_id):
 return bool(org_id() and one('select r.id from rooms r join floors f on f.id=r.floor_id join buildings b on b.id=f.building_id where r.id=? and b.organization_id=?',(room_id,org_id())))

def owns_workorder(workorder_id):
 return bool(org_id() and one('select w.id from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where w.id=? and b.organization_id=?',(workorder_id,org_id())))

def owns_incident(incident_id):
 return bool(org_id() and one('select i.id from incidents i join assets a on a.id=i.asset_id join buildings b on b.id=a.building_id where i.id=? and b.organization_id=?',(incident_id,org_id())))

def owns_user(user_id):
 return bool(org_id() and one('select id from users where id=? and organization_id=?',(user_id,org_id())))

def support_access_active(org):
 if not org or not org['support_access_enabled']: return False
 until=org['support_access_until']
 if not until: return True
 try:
  dt=datetime.fromisoformat(str(until).replace('Z','+00:00'))
  now=datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
  return dt>=now
 except Exception:
  return False

def customer_access(target_org_id,action,reason=''):
 try:
  writer=x if target_org_id==org_id() else x_system
  writer('insert into customer_access_log(target_organization_id,actor_user_id,actor_name,action,reason,ip) values(?,?,?,?,?,?)',(target_org_id,session.get('user_id'),session.get('user_name','Systém'),action,(reason or '')[:500],request.headers.get('X-Forwarded-For',request.remote_addr or '')))
 except Exception:
  pass

def plan_limits(oid=None):
 oid=oid or org_id()
 org=one('select plan from organizations where id=?',(oid,)) if oid else None
 return PLAN_LIMITS.get((org['plan'] if org else 'BASIC') or 'BASIC',PLAN_LIMITS['BASIC'])

def resource_count(resource,oid=None):
 oid=oid or org_id()
 if resource=='users': return int(one('select count(*) n from users where organization_id=?',(oid,))['n'])
 if resource=='buildings': return int(one('select count(*) n from buildings where organization_id=?',(oid,))['n'])
 if resource=='assets': return int(one('select count(*) n from assets a join buildings b on b.id=a.building_id where b.organization_id=?',(oid,))['n'])
 return 0

def plan_allows(resource,oid=None):
 limit=plan_limits(oid).get(resource)
 return limit is None or resource_count(resource,oid)<limit

def asset_event(asset_id,event_type,title,detail=''):
 try:
  x('insert into asset_events(asset_id,organization_id,user_id,user_name,event_type,title,detail) values(?,?,?,?,?,?,?)',(asset_id,org_id(),session.get('user_id'),session.get('user_name','Systém'),event_type,title,detail))
 except Exception:
  pass

def audit(action,detail=''):
 try:
  x("insert into audit_log(user_id,user_name,action,detail,ip,organization_id) values(?,?,?,?,?,?)",(session.get('user_id'),session.get('user_name','Systém'),action,detail,request.headers.get('X-Forwarded-For',request.remote_addr or ''),org_id()))
 except Exception:
  pass
DATABASE_URL=os.environ.get('DATABASE_URL','').strip()
USING_POSTGRES=bool(DATABASE_URL)
def _sql(sql):
 return sql.replace('datetime(\'now\')','CURRENT_TIMESTAMP').replace("date('now')",'CURRENT_DATE').replace('?','%s') if USING_POSTGRES else sql
def con(system=False):
 if USING_POSTGRES:
  if not psycopg: raise RuntimeError('DATABASE_URL is set but psycopg is not installed')
  db=psycopg.connect(DATABASE_URL,row_factory=dict_row)
  if system or not has_request_context():
   oid=''; platform_admin='1'
  else:
   oid=str(org_id() or '')
   platform_admin='0'
  db.execute("select set_config('gamo.organization_id',%s,false)",(oid,))
  db.execute("select set_config('gamo.platform_admin',%s,false)",(platform_admin,))
  return db
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def q(sql,a=()):
 with con() as c:return c.execute(_sql(sql),a).fetchall()
def one(sql,a=()):
 with con() as c:return c.execute(_sql(sql),a).fetchone()
def one_system(sql,a=()):
 with con(system=True) as c:return c.execute(_sql(sql),a).fetchone()
def q_system(sql,a=()):
 with con(system=True) as c:return c.execute(_sql(sql),a).fetchall()
def x(sql,a=()):
 with con() as c:
  statement=_sql(sql)
  lower=statement.lstrip().lower()
  no_id_tables=('insert into settings','insert into organization_settings','insert into platform_meta','insert into schema_migrations')
  if USING_POSTGRES and lower.startswith('insert into') and not lower.startswith(no_id_tables) and ' returning ' not in lower:
   statement+=' RETURNING id'
   r=c.execute(statement,a); row=r.fetchone(); c.commit(); return row['id'] if row else None
  r=c.execute(statement,a); c.commit(); return r.lastrowid if not USING_POSTGRES else r.rowcount
def x_system(sql,a=()):
 with con(system=True) as c:
  statement=_sql(sql)
  lower=statement.lstrip().lower()
  no_id_tables=('insert into settings','insert into organization_settings','insert into platform_meta','insert into schema_migrations')
  if USING_POSTGRES and lower.startswith('insert into') and not lower.startswith(no_id_tables) and ' returning ' not in lower:
   statement+=' RETURNING id'
   r=c.execute(statement,a); row=r.fetchone(); c.commit(); return row['id'] if row else None
  r=c.execute(statement,a); c.commit(); return r.lastrowid if not USING_POSTGRES else r.rowcount
def init_postgres():
 schema=[
  """CREATE TABLE IF NOT EXISTS buildings(id BIGSERIAL PRIMARY KEY,code TEXT UNIQUE,name TEXT,address TEXT,manager TEXT,customer TEXT DEFAULT 'GAMO a.s.',status TEXT DEFAULT 'Aktívna')""",
  """CREATE TABLE IF NOT EXISTS floors(id BIGSERIAL PRIMARY KEY,building_id BIGINT REFERENCES buildings(id) ON DELETE CASCADE,code TEXT,name TEXT)""",
  """CREATE TABLE IF NOT EXISTS rooms(id BIGSERIAL PRIMARY KEY,floor_id BIGINT REFERENCES floors(id) ON DELETE CASCADE,code TEXT,name TEXT,area DOUBLE PRECISION,tenant TEXT,zone TEXT)""",
  """CREATE TABLE IF NOT EXISTS assets(id BIGSERIAL PRIMARY KEY,asset_id TEXT UNIQUE,name TEXT,building_id BIGINT,floor_id BIGINT,room_id BIGINT,profession TEXT,grp TEXT,type TEXT,manufacturer TEXT,model TEXT,serial TEXT,system_id TEXT,parent_id BIGINT,status TEXT,criticality TEXT,service_months INTEGER,revision_months INTEGER,purchase_price DOUBLE PRECISION,installed TEXT,warranty TEXT,ip TEXT,protocol TEXT,notes TEXT)""",
  """CREATE TABLE IF NOT EXISTS workorders(id BIGSERIAL PRIMARY KEY,asset_id BIGINT,title TEXT,kind TEXT,priority TEXT,status TEXT,due TEXT,supplier TEXT,technician TEXT,cost DOUBLE PRECISION,description TEXT)""",
  """CREATE TABLE IF NOT EXISTS incidents(id BIGSERIAL PRIMARY KEY,asset_id BIGINT,title TEXT,severity TEXT,status TEXT,reported TEXT,impact TEXT,cause TEXT,cost DOUBLE PRECISION)""",
  """CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY,name TEXT,email TEXT,role TEXT,status TEXT,password_hash TEXT,last_login TEXT)""",
  """CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT)""",
  """CREATE TABLE IF NOT EXISTS audit_log(id BIGSERIAL PRIMARY KEY,created TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,user_id BIGINT,user_name TEXT,action TEXT,detail TEXT,ip TEXT)""",
  """CREATE TABLE IF NOT EXISTS documents(id BIGSERIAL PRIMARY KEY,building_id BIGINT REFERENCES buildings(id) ON DELETE CASCADE,name TEXT,category TEXT,mime TEXT,size BIGINT,uploaded TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,data BYTEA)""",
  """CREATE TABLE IF NOT EXISTS organizations(id BIGSERIAL PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,status TEXT DEFAULT 'Aktívny',plan TEXT DEFAULT 'INTERNAL',license_status TEXT DEFAULT 'Aktívna',license_until TEXT,branding_name TEXT,brand_color TEXT DEFAULT '#E31B23',brand_tagline TEXT DEFAULT 'FACILITY MANAGEMENT',created TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)""",
  """CREATE TABLE IF NOT EXISTS platform_meta(k TEXT PRIMARY KEY,v TEXT)"""
 ]
 with con() as db:
  for statement in schema: db.execute(statement)
  db.execute("ALTER TABLE buildings ADD COLUMN IF NOT EXISTS customer TEXT DEFAULT 'GAMO a.s.'")
  db.execute("ALTER TABLE buildings ADD COLUMN IF NOT EXISTS organization_id BIGINT")
  db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id BIGINT")
  db.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS brand_color TEXT DEFAULT '#E31B23'")
  db.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS brand_tagline TEXT DEFAULT 'FACILITY MANAGEMENT'")
  db.execute("INSERT INTO organizations(code,name,status,plan,license_status,branding_name) VALUES('GAMO','GAMO a.s.','Aktívny','INTERNAL','Aktívna','GAMO a.s.') ON CONFLICT (code) DO NOTHING")
  gamo_org=db.execute("SELECT id FROM organizations WHERE code='GAMO'").fetchone()['id']
  db.execute("UPDATE users SET organization_id=%s WHERE organization_id IS NULL",(gamo_org,))
  db.execute("UPDATE buildings SET organization_id=%s WHERE organization_id IS NULL",(gamo_org,))
  db.commit()
 run_migrations(con, True)
 if not one('select count(*) n from users')['n']:
  x('insert into users(name,email,role,status,password_hash,organization_id) values(?,?,?,?,?,?)',('GAMO Administrator','admin@gamo.sk','Administrator','Aktívny',generate_password_hash(os.environ.get('GAMO_ADMIN_PASSWORD','GamoFM2026!')),gamo_org))
def init():
 os.makedirs(DATA_DIR,exist_ok=True)
 if USING_POSTGRES:
  init_postgres(); return
 with con() as c:
  c.executescript("""CREATE TABLE IF NOT EXISTS buildings(id INTEGER PRIMARY KEY,code TEXT UNIQUE,name TEXT,address TEXT,manager TEXT,customer TEXT DEFAULT 'GAMO a.s.',status TEXT DEFAULT 'Aktívna');CREATE TABLE IF NOT EXISTS floors(id INTEGER PRIMARY KEY,building_id INTEGER REFERENCES buildings(id) ON DELETE CASCADE,code TEXT,name TEXT);CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY,floor_id INTEGER REFERENCES floors(id) ON DELETE CASCADE,code TEXT,name TEXT,area REAL,tenant TEXT,zone TEXT);CREATE TABLE IF NOT EXISTS assets(id INTEGER PRIMARY KEY,asset_id TEXT UNIQUE,name TEXT,building_id INTEGER,floor_id INTEGER,room_id INTEGER,profession TEXT,grp TEXT,type TEXT,manufacturer TEXT,model TEXT,serial TEXT,system_id TEXT,parent_id INTEGER,status TEXT,criticality TEXT,service_months INTEGER,revision_months INTEGER,purchase_price REAL,installed TEXT,warranty TEXT,ip TEXT,protocol TEXT,notes TEXT);CREATE TABLE IF NOT EXISTS workorders(id INTEGER PRIMARY KEY,asset_id INTEGER,title TEXT,kind TEXT,priority TEXT,status TEXT,due TEXT,supplier TEXT,technician TEXT,cost REAL,description TEXT);CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY,asset_id INTEGER,title TEXT,severity TEXT,status TEXT,reported TEXT,impact TEXT,cause TEXT,cost REAL);CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT,role TEXT,status TEXT);CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT);""")
  bcols=[r[1] for r in c.execute("pragma table_info(buildings)").fetchall()]
  if 'customer' not in bcols: c.execute("alter table buildings add column customer TEXT DEFAULT 'GAMO a.s.'")
  cols=[r[1] for r in c.execute("pragma table_info(users)").fetchall()]
  if 'password_hash' not in cols: c.execute("alter table users add column password_hash TEXT")
  if 'last_login' not in cols: c.execute("alter table users add column last_login TEXT")
  c.execute("""CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY,created TEXT DEFAULT CURRENT_TIMESTAMP,user_id INTEGER,user_name TEXT,action TEXT,detail TEXT,ip TEXT);""")
  c.execute("""CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY,building_id INTEGER REFERENCES buildings(id) ON DELETE CASCADE,name TEXT,category TEXT,mime TEXT,size INTEGER,uploaded TEXT DEFAULT CURRENT_TIMESTAMP,data BLOB);""")
  c.execute("""CREATE TABLE IF NOT EXISTS organizations(id INTEGER PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,status TEXT DEFAULT 'Aktívny',plan TEXT DEFAULT 'INTERNAL',license_status TEXT DEFAULT 'Aktívna',license_until TEXT,branding_name TEXT,brand_color TEXT DEFAULT '#E31B23',brand_tagline TEXT DEFAULT 'FACILITY MANAGEMENT',created TEXT DEFAULT CURRENT_TIMESTAMP);""")
  orgcols=[r[1] for r in c.execute("pragma table_info(organizations)").fetchall()]
  if 'brand_color' not in orgcols: c.execute("alter table organizations add column brand_color TEXT DEFAULT '#E31B23'")
  if 'brand_tagline' not in orgcols: c.execute("alter table organizations add column brand_tagline TEXT DEFAULT 'FACILITY MANAGEMENT'")
  c.execute("""CREATE TABLE IF NOT EXISTS platform_meta(k TEXT PRIMARY KEY,v TEXT);""")
  bcols=[r[1] for r in c.execute("pragma table_info(buildings)").fetchall()]
  if 'organization_id' not in bcols: c.execute("alter table buildings add column organization_id INTEGER")
  ucols=[r[1] for r in c.execute("pragma table_info(users)").fetchall()]
  if 'organization_id' not in ucols: c.execute("alter table users add column organization_id INTEGER")
  c.execute("insert or ignore into organizations(code,name,status,plan,license_status,branding_name) values('GAMO','GAMO a.s.','Aktívny','INTERNAL','Aktívna','GAMO a.s.')")
  gamo_org=c.execute("select id from organizations where code='GAMO'").fetchone()[0]
  c.execute("update users set organization_id=? where organization_id is null",(gamo_org,))
  c.execute("update buildings set organization_id=? where organization_id is null",(gamo_org,))
  if not c.execute('select count(*) n from buildings').fetchone()['n']:
   c.execute("insert into buildings(code,name,address,manager,organization_id) values('A','GAMO Centrum – Budova A','Kyjevské námestie 6, Banská Bystrica','Facility Management',?)",(gamo_org,)); c.execute("insert into buildings(code,name,address,manager,organization_id) values('B','GAMO Centrum – Budova B','Banská Bystrica','Facility Management',?)",(gamo_org,))
   a=c.execute("select id from buildings where code='A'").fetchone()[0]; b=c.execute("select id from buildings where code='B'").fetchone()[0]
   f1=c.execute("insert into floors(building_id,code,name) values(?,?,?)",(a,'1.NP','Prízemie')).lastrowid; f2=c.execute("insert into floors(building_id,code,name) values(?,?,?)",(a,'2.NP','Administratíva')).lastrowid; fb=c.execute("insert into floors(building_id,code,name) values(?,?,?)",(b,'1.NP','Technické podlažie')).lastrowid
   r1=c.execute("insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",(f1,'A005','Kancelária',28.5,'GAMO','HVAC zóna 01')).lastrowid;r2=c.execute("insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",(f1,'A008','Kancelária',31.2,'GAMO','HVAC zóna 01')).lastrowid;r3=c.execute("insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",(f2,'A214','Serverovňa',18,'GAMO','IT kritická zóna')).lastrowid;r4=c.execute("insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",(fb,'B202','Technická miestnosť',42,'','HVAC zóna B')).lastrowid
   p=c.execute("insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,serial,system_id,status,criticality,service_months,revision_months,purchase_price,ip,protocol) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",('HVAC-000001','VRV vonkajšia jednotka',a,f1,r1,'HVAC','VRV systém','VRV-OUT','Daikin','RXYQ','SN240001','HVAC-A-VRV-01','Prevádzka','A',6,12,8900,'','Modbus')).lastrowid
   c.execute("insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,system_id,parent_id,status,criticality,purchase_price) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",('HVAC-000002','VRV vnútorná jednotka A005',a,f1,r1,'HVAC','VRV systém','VRV-IN','Daikin','FXZQ25','HVAC-A-VRV-01',p,'Prevádzka','B',1450));c.execute("insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,system_id,parent_id,status,criticality,purchase_price) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",('HVAC-000003','VRV vnútorná jednotka A008',a,f1,r2,'HVAC','VRV systém','VRV-IN','Daikin','FXZQ25','HVAC-A-VRV-01',p,'Prevádzka','B',1450));c.execute("insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,system_id,status,criticality,purchase_price,ip,protocol) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",('SLB-000001','Core switch serverovne',a,f2,r3,'SLB','LAN/WAN','Switch','Cisco','Catalyst','SLB-A-LAN-01','Prevádzka','A',3200,'10.0.1.2','SNMP'))
   c.execute("insert into workorders(asset_id,title,kind,priority,status,due,supplier,technician,cost,description) values(?,?,?,?,?,?,?,?,?,?)",(p,'Preventívny servis VRV','PM','Stredná','Plánované',str(date.today()+timedelta(days=12)),'Servis HVAC s.r.o.','Ján Technik',350,'Kontrola systému a filtrov'))
   c.execute("insert into incidents(asset_id,title,severity,status,reported,impact,cost) values(?,?,?,?,?,?,?)",(p,'Kolísanie tlaku VRV','Porucha','Otvorená',str(date.today()),'A005, A008 – znížený komfort',0))
   c.execute("insert into users(name,email,role,status,password_hash,organization_id) values(?,?,?,?,?,?)",('GAMO Administrator','admin@gamo.sk','Administrator','Aktívny',generate_password_hash(os.environ.get('GAMO_ADMIN_PASSWORD','GamoFM2026!')),gamo_org))
 run_migrations(con, False)
init()
with con() as c:
 c.execute(_sql("update users set password_hash=? where (password_hash is null or password_hash='') and lower(email)=?"),(generate_password_hash(os.environ.get('GAMO_ADMIN_PASSWORD','GamoFM2026!')),'admin@gamo.sk')); c.commit()

@app.after_request
def security_headers(response):
 response.headers['X-Content-Type-Options']='nosniff'
 response.headers['X-Frame-Options']='DENY'
 response.headers['Referrer-Policy']='same-origin'
 response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
 response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
 if app.config.get('SESSION_COOKIE_SECURE'):
  response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
 if request.path.startswith('/backup') or request.path.endswith('/backup') or request.path.startswith('/privacy'):
  response.headers['Cache-Control']='no-store, private'
 return response

@app.before_request
def require_login():
 if request.endpoint in ('login','static') or request.path.startswith('/static/'): return
 if not session.get('user_id'): return redirect(url_for('login',next=request.path))
 current=one_system('select id,status,role,organization_id from users where id=?',(session.get('user_id'),))
 if not current or current['status']!='Aktívny' or current['organization_id']!=actor_org_id():
  session.clear(); return redirect(url_for('login'))
 if current['role']!=session.get('user_role'):
  session['user_role']=current['role']
 actor_org=one_system('select * from organizations where id=?',(actor_org_id(),)) if actor_org_id() else None
 if actor_org: session['organization_code']=actor_org['code']
 target=None
 if support_mode():
  target=one_system('select * from organizations where id=?',(session.get('support_target_org_id'),))
  if not actor_org or actor_org['code']!='GAMO' or current['role']!='Administrator' or not target or not support_access_active(target):
   session.pop('support_target_org_id',None); session.pop('support_target_name',None); session.pop('support_target_code',None); target=None
 org=target or actor_org
 license_ok=bool(org and org['status']=='Aktívny' and org['license_status']=='Aktívna' and (not org['license_until'] or str(org['license_until'])[:10]>=date.today().isoformat()))
 if not license_ok:
  session.clear()
  return redirect(url_for('login'))
 if request.method in {'POST','PUT','PATCH','DELETE'}:
  supplied=request.form.get('_csrf') or request.headers.get('X-CSRF-Token','')
  expected=session.get('csrf','')
  if not supplied or not expected or not secrets.compare_digest(str(supplied),str(expected)):
   abort(400,description='Neplatný bezpečnostný token požiadavky.')
 role=session.get('user_role','Viewer')
 if request.path.startswith('/admin') or request.path.startswith('/settings/') or request.endpoint in {'admin','update_user'}:
  if not can('users_manage') and not can('settings_manage'):
   flash('Na túto časť nemáš administrátorské oprávnenie.','error'); return redirect('/')
 if request.method in {'POST','PUT','PATCH','DELETE'}:
  what=(request.view_args or {}).get('what')
  needed={'user':'users_manage','building':'facility_write','floor':'facility_write','room':'facility_write','asset':'asset_write','workorder':'maintenance_write','incident':'incident_write'}.get(what)
  endpoint_permissions={
   'upload_building_document':'documents_write','delete_document':'documents_write','save_setting':'settings_manage',
   'update_user':'users_manage','platform_customer':'platform_manage','platform_customer_update':'platform_manage',
   'platform_customer_branding':'platform_manage'
  }
  needed=endpoint_permissions.get(request.endpoint,needed)
  if needed and not can(needed):
   flash('Tvoja rola nemá oprávnenie vykonať túto zmenu.','error'); return redirect(request.referrer or '/')

@app.route('/login',methods=['GET','POST'])
def login():
 if session.get('user_id'): return redirect('/')
 error=None
 if request.method=='POST':
  email=(request.form.get('email') or '').strip().lower(); password=request.form.get('password') or ''; remember=request.form.get('remember')=='1'
  key=(request.headers.get('X-Forwarded-For',request.remote_addr or '')+'|'+email)
  now=time.time(); attempts=[t for t in _login_attempts.get(key,[]) if now-t<LOGIN_WINDOW]
  if len(attempts)>=LOGIN_MAX_ATTEMPTS:
   return render_template('login.html',error='Príliš veľa neúspešných pokusov. Skús to znova o pár minút.'),429
  u=one_system('select * from users where lower(email)=?',(email,))
  if u and u['status']=='Aktívny' and u['password_hash'] and check_password_hash(u['password_hash'],password):
   org=one_system('select * from organizations where id=?',(u['organization_id'],)) if u['organization_id'] else None
   license_ok=bool(org and org['status']=='Aktívny' and org['license_status']=='Aktívna' and (not org['license_until'] or str(org['license_until'])[:10]>=date.today().isoformat()))
   if not license_ok:
    error='Licencia organizácie nie je aktívna alebo jej platnosť skončila. Kontaktuj GAMO.'
   else:
    _login_attempts.pop(key,None); session.clear(); session.permanent=remember
    session['user_id']=u['id']; session['user_name']=u['name']; session['user_role']=u['role']; session['organization_id']=u['organization_id']; session['organization_code']=org['code']; session['csrf']=secrets.token_urlsafe(32)
    x("update users set last_login=datetime('now') where id=?",(u['id'],))
    return redirect(request.args.get('next') or '/')
  else:
   attempts.append(now); _login_attempts[key]=attempts; error='Nesprávny e-mail alebo heslo.'
 return render_template('login.html',error=error)

@app.get('/logout')
def logout():
 session.clear(); return redirect('/login')

@app.context_processor
def ctx():
 org=one('select * from organizations where id=?',(org_id(),)) if org_id() else None
 brand_name=(org['branding_name'] or org['name']) if org else 'GAMO a.s.'
 brand_color=(org['brand_color'] or '#E31B23') if org else '#E31B23'
 brand_tagline=(org['brand_tagline'] or 'FACILITY MANAGEMENT') if org else 'FACILITY MANAGEMENT'
 return dict(today=date.today(),csrf_token=session.get('csrf',''),current_user={'name':session.get('user_name',''),'role':session.get('user_role',''),'organization_id':actor_org_id()},current_org=org,brand_name=brand_name,brand_color=brand_color,brand_tagline=brand_tagline,is_gamo_admin=is_gamo_admin(),support_mode=support_mode(),support_customer_name=session.get('support_target_name',''),can=can)

@app.route('/onboarding',methods=['GET','POST'])
def onboarding():
 org=one('select * from organizations where id=?',(org_id(),))
 if not org or org['code']=='GAMO': return redirect('/')
 if session.get('user_role')!='Administrator':
  return redirect('/')
 if request.method=='POST':
  code=(request.form.get('code') or '').strip().upper()
  name=(request.form.get('name') or '').strip()
  address=(request.form.get('address') or '').strip()
  manager=(request.form.get('manager') or session.get('user_name','')).strip()
  try: floors=max(1,min(50,int(request.form.get('floors_count') or 1)))
  except ValueError: floors=1
  if not code or not name:
   flash('Kód a názov prvej budovy sú povinné.','error')
  elif not plan_allows('buildings'):
   flash('Licenčný plán už neumožňuje pridať ďalšiu budovu.','error')
  elif one('select id from buildings where organization_id=? and upper(code)=?',(org_id(),code)):
   flash('Budova s týmto kódom už existuje.','error')
  else:
   bid=x('insert into buildings(code,name,address,manager,customer,organization_id) values(?,?,?,?,?,?)',(code,name,address,manager,org['name'],org_id()))
   for n in range(1,floors+1):
    x('insert into floors(building_id,code,name) values(?,?,?)',(bid,f'{n}.NP',f'{n}. nadzemné podlažie'))
   x('update organizations set onboarding_complete=? where id=?',(True if USING_POSTGRES else 1,org_id()))
   audit('ONBOARDING_COMPLETE',f'{name} · {floors} podlaží')
   flash('Firemné prostredie je pripravené. Teraz môžeš doplniť miestnosti a assety.','success')
   return redirect(f'/building/{bid}')
 limits=plan_limits()
 return render_template('onboarding.html',org=org,limits=limits,csrf_token=session.get('csrf',''))

@app.post('/onboarding/skip')
def onboarding_skip():
 org=one('select * from organizations where id=?',(org_id(),))
 if not org or org['code']=='GAMO' or session.get('user_role')!='Administrator': abort(403)
 x('update organizations set onboarding_complete=? where id=?',(True if USING_POSTGRES else 1,org_id()))
 audit('ONBOARDING_SKIP','Onboarding preskočený administrátorom')
 return redirect('/')

@app.route('/')
def dashboard():
 oid=org_id()
 org=one('select * from organizations where id=?',(oid,)) if oid else None
 if org and org['code']!='GAMO' and session.get('user_role')=='Administrator' and not bool(org['onboarding_complete']):
  return redirect('/onboarding')
 s={
  'assets':one('select count(*) n from assets a join buildings b on b.id=a.building_id where b.organization_id=?',(oid,))['n'],
  'buildings':one('select count(*) n from buildings where organization_id=?',(oid,))['n'],
  'rooms':one('select count(*) n from rooms r join floors f on f.id=r.floor_id join buildings b on b.id=f.building_id where b.organization_id=?',(oid,))['n'],
  'open':one("select count(*) n from incidents i join assets a on a.id=i.asset_id join buildings b on b.id=a.building_id where b.organization_id=? and i.status!='Ukončená'",(oid,))['n'],
  'critical':one("select count(*) n from assets a join buildings b on b.id=a.building_id where b.organization_id=? and a.criticality='A'",(oid,))['n'],
  'orders':one("select count(*) n from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=? and w.status!='Ukončené'",(oid,))['n'],
  'high_incidents':one("select count(*) n from incidents i join assets a on a.id=i.asset_id join buildings b on b.id=a.building_id where b.organization_id=? and i.status!='Ukončená' and i.severity in ('Vysoká','Kritická','Havária')",(oid,))['n'],
  'overdue':one("select count(*) n from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=? and w.status!='Ukončené' and w.due is not null and w.due!='' and date(w.due)<date('now')",(oid,))['n']
 }
 report={
  'maintenance_cost':one('select coalesce(sum(w.cost),0) n from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=?',(oid,))['n'],
  'incident_cost':one('select coalesce(sum(i.cost),0) n from incidents i join assets a on a.id=i.asset_id join buildings b on b.id=a.building_id where b.organization_id=?',(oid,))['n'],
  'closed_orders':one("select count(*) n from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=? and w.status='Ukončené'",(oid,))['n'],
  'total_orders':one('select count(*) n from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=?',(oid,))['n']
 }; report['total_cost']=report['maintenance_cost']+report['incident_cost']
 profession_sql="select coalesce(a.profession,'Iné') label,round(coalesce(sum(w.cost),0)::numeric,2) value from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=? group by a.profession order by value desc limit 6" if USING_POSTGRES else "select coalesce(a.profession,'Iné') label,round(coalesce(sum(w.cost),0),2) value from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=? group by a.profession order by value desc limit 6"
 return render_template('index.html',page='dashboard',s=s,report=report,profession_costs=q(profession_sql,(oid,)),buildings=q('select * from buildings where organization_id=?',(oid,)),recent=q('select w.*,a.asset_id,a.name asset from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=? order by w.id desc limit 6',(oid,)),incidents=q('select i.*,a.asset_id from incidents i join assets a on a.id=i.asset_id join buildings b on b.id=a.building_id where b.organization_id=? order by i.id desc limit 5',(oid,)))
@app.route('/reports')
def reports():
 if not can('reports_view'): abort(403)
 oid=org_id()
 stats={
  'assets':one('select count(*) n from assets a join buildings b on b.id=a.building_id where b.organization_id=?',(oid,))['n'],
  'maintenance_cost':one('select coalesce(sum(w.cost),0) n from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=?',(oid,))['n'],
  'incident_cost':one('select coalesce(sum(i.cost),0) n from incidents i join assets a on a.id=i.asset_id join buildings b on b.id=a.building_id where b.organization_id=?',(oid,))['n'],
  'open_incidents':one("select count(*) n from incidents i join assets a on a.id=i.asset_id join buildings b on b.id=a.building_id where b.organization_id=? and i.status!='Ukončená'",(oid,))['n'],
  'overdue':one("select count(*) n from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=? and w.status!='Ukončené' and w.due is not null and w.due!='' and date(w.due)<date('now')",(oid,))['n']
 }
 stats['total_cost']=stats['maintenance_cost']+stats['incident_cost']
 building_rows=q("""select b.id,b.code,b.name,
  (select count(*) from assets a where a.building_id=b.id) assets,
  (select coalesce(sum(w.cost),0) from workorders w join assets a on a.id=w.asset_id where a.building_id=b.id) maintenance_cost,
  (select coalesce(sum(i.cost),0) from incidents i join assets a on a.id=i.asset_id where a.building_id=b.id) incident_cost,
  (select count(*) from incidents i join assets a on a.id=i.asset_id where a.building_id=b.id and i.status!='Ukončená') open_incidents
  from buildings b where b.organization_id=? order by b.name""",(oid,))
 profession_rows=q("""select coalesce(a.profession,'Iné') profession,count(*) assets,
  coalesce(sum(a.purchase_price),0) asset_value
  from assets a join buildings b on b.id=a.building_id
  where b.organization_id=? group by a.profession order by assets desc""",(oid,))
 return render_template('index.html',page='reports',report_stats=stats,report_buildings=building_rows,report_professions=profession_rows)

@app.get('/reports/export.xlsx')
def reports_export_xlsx():
 if not can('reports_view'): abort(403)
 oid=org_id(); org=one('select * from organizations where id=?',(oid,))
 brand=(org['brand_color'] if org and org['brand_color'] else '#17365D').replace('#','').upper()
 if len(brand)!=6 or any(ch not in '0123456789ABCDEF' for ch in brand): brand='17365D'
 dark='17365D'; blue='246BFD'; light='EAF1FB'; pale='F7F9FC'; green='DFF3E8'; red='FCE8EC'; amber='FFF3D8'; white='FFFFFF'; gray='667085'
 wb=Workbook(); ws=wb.active; ws.title='Súhrn'
 wb.properties.creator='GAMO Facility Platform'
 wb.properties.title=f"Facility report · {org['name'] if org else ''}"
 wb.properties.subject='Assety, údržba, incidenty a manažérske KPI'
 thin=Side(style='thin',color='DDE3EC')
 money_fmt='#,##0.00 [$€-sk-SK]'
 date_fmt='dd.mm.yyyy'

 def excel_safe(value):
  if isinstance(value,str) and value[:1] in {'=','+','-','@'}: return "'" + value
  return value

 def excel_date(value):
  if not value: return None
  if isinstance(value,(date,datetime)): return value
  try: return datetime.strptime(str(value)[:10],'%Y-%m-%d').date()
  except Exception: return excel_safe(value)

 buildings=q("""select b.id,b.code,b.name,
  (select count(*) from assets a where a.building_id=b.id) assets,
  (select coalesce(sum(w.cost),0) from workorders w join assets a on a.id=w.asset_id where a.building_id=b.id) maintenance_cost,
  (select coalesce(sum(i.cost),0) from incidents i join assets a on a.id=i.asset_id where a.building_id=b.id) incident_cost,
  (select count(*) from incidents i join assets a on a.id=i.asset_id where a.building_id=b.id and i.status!='Ukončená') open_incidents
  from buildings b where b.organization_id=? order by b.name""",(oid,))
 professions=q("""select coalesce(a.profession,'Iné') profession,count(*) assets,
  coalesce(sum(a.purchase_price),0) asset_value
  from assets a join buildings b on b.id=a.building_id
  where b.organization_id=? group by a.profession order by assets desc""",(oid,))
 assets_rows=q("""select a.asset_id,a.name,b.name building,f.code floor,r.code room,a.profession,a.grp,a.type,a.manufacturer,a.model,a.serial,a.system_id,a.status,a.criticality,a.purchase_price
  from assets a join buildings b on b.id=a.building_id left join floors f on f.id=a.floor_id left join rooms r on r.id=a.room_id
  where b.organization_id=? order by a.asset_id""",(oid,))
 wo_rows=q("""select a.asset_id,a.name asset,b.name building,w.title,w.kind,w.priority,w.status,w.due,w.supplier,w.technician,w.cost,w.description
  from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id
  where b.organization_id=? order by w.id desc""",(oid,))
 inc_rows=q("""select a.asset_id,a.name asset,b.name building,i.title,i.severity,i.status,i.reported,i.impact,i.cause,i.cost
  from incidents i join assets a on a.id=i.asset_id join buildings b on b.id=a.building_id
  where b.organization_id=? order by i.id desc""",(oid,))
 overdue_rows=[r for r in wo_rows if r['status']!='Ukončené' and r['due'] and str(r['due'])[:10]<date.today().isoformat()]

 maintenance_cost=float(sum(float(r['cost'] or 0) for r in wo_rows))
 incident_cost=float(sum(float(r['cost'] or 0) for r in inc_rows))
 total_cost=maintenance_cost+incident_cost
 open_incidents=sum(1 for r in inc_rows if r['status']!='Ukončená')

 # Executive summary
 ws.sheet_view.showGridLines=False
 ws.freeze_panes='A12'
 ws.merge_cells('A1:H2')
 ws['A1']=f"GAMO FACILITY REPORT · {org['name'] if org else ''}"
 ws['A1'].font=Font(color=white,bold=True,size=20)
 ws['A1'].fill=PatternFill('solid',fgColor=brand or dark)
 ws['A1'].alignment=Alignment(vertical='center')
 for row in ws['A1:H2']:
  for cell in row: cell.fill=PatternFill('solid',fgColor=brand or dark)
 ws.row_dimensions[1].height=25; ws.row_dimensions[2].height=16
 ws.merge_cells('A3:H3'); ws['A3']=f"Generované {datetime.now().strftime('%d.%m.%Y %H:%M')} · {org['plan'] if org else ''} · organizácia {org['code'] if org else ''}"
 ws['A3'].font=Font(color=gray,size=9); ws['A3'].alignment=Alignment(vertical='center')

 cards=[
  ('A5','B7','CELKOVÉ NÁKLADY',total_cost,money_fmt,brand or dark),
  ('C5','D7','ÚDRŽBA',maintenance_cost,money_fmt,blue),
  ('E5','F7','OTVORENÉ INCIDENTY',open_incidents,'0','C0394E' if open_incidents else '16845A'),
  ('G5','H7','PO TERMÍNE',len(overdue_rows),'0','C98412' if overdue_rows else '16845A')
 ]
 for start,end,label,value,numfmt,color in cards:
  ws.merge_cells(f'{start}:{end}')
  cell=ws[start]; cell.value=value; cell.number_format=numfmt
  cell.font=Font(size=17,bold=True,color=dark)
  cell.fill=PatternFill('solid',fgColor=pale)
  cell.alignment=Alignment(horizontal='center',vertical='center')
  cell.border=Border(left=Side(style='medium',color=color),top=thin,right=thin,bottom=thin)
  label_cell=ws.cell(cell.row-1,cell.column); label_cell.value=label; label_cell.font=Font(size=8,bold=True,color=gray)

 ws['A9']='PORTFÓLIO'; ws['A9'].font=Font(size=9,bold=True,color=gray)
 portfolio=[('Budovy',len(buildings)),('Assety',len(assets_rows)),('Servisné záznamy',len(wo_rows)),('Incidenty',len(inc_rows))]
 for idx,(label,value) in enumerate(portfolio):
  col=1+idx*2
  ws.cell(9,col,label).font=Font(size=8,bold=True,color=gray)
  ws.cell(9,col+1,value).font=Font(size=11,bold=True,color=dark)

 # Building cost table
 headers=['Kód','Budova','Assety','Údržba','Incidenty','Otvorené','Spolu']
 start_row=11
 for col,hdr in enumerate(headers,1):
  cell=ws.cell(start_row,col,hdr); cell.fill=PatternFill('solid',fgColor=dark); cell.font=Font(color=white,bold=True,size=9); cell.alignment=Alignment(vertical='center')
 for r_idx,b in enumerate(buildings,start_row+1):
  total=float(b['maintenance_cost'] or 0)+float(b['incident_cost'] or 0)
  vals=[excel_safe(b['code']),excel_safe(b['name']),b['assets'],float(b['maintenance_cost'] or 0),float(b['incident_cost'] or 0),b['open_incidents'],total]
  for col,val in enumerate(vals,1):
   cell=ws.cell(r_idx,col,val); cell.border=Border(bottom=thin); cell.alignment=Alignment(vertical='top',wrap_text=True)
  for col in (4,5,7): ws.cell(r_idx,col).number_format=money_fmt
  if b['open_incidents']: ws.cell(r_idx,6).fill=PatternFill('solid',fgColor=red)
 end_row=max(start_row+1,start_row+len(buildings))
 if buildings:
  tab=Table(displayName='BuildingCostTable',ref=f'A{start_row}:G{end_row}')
  tab.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True,showFirstColumn=False,showLastColumn=False)
  ws.add_table(tab)

 # Charts use a dedicated hidden data sheet so chart anchors stay visible.
 chart_data=wb.create_sheet('_Grafy'); chart_data.sheet_state='hidden'
 chart_data.append(['Budova','Údržba','Incidenty','','Profesia','Assety'])
 chart_buildings=sorted(buildings,key=lambda b:float(b['maintenance_cost'] or 0)+float(b['incident_cost'] or 0),reverse=True)[:12]
 chart_professions=list(professions)[:10]
 for idx,b in enumerate(chart_buildings,2):
  chart_data.cell(idx,1,excel_safe(b['code'])); chart_data.cell(idx,2,float(b['maintenance_cost'] or 0)); chart_data.cell(idx,3,float(b['incident_cost'] or 0))
 for idx,p in enumerate(chart_professions,2):
  chart_data.cell(idx,5,excel_safe(p['profession'])); chart_data.cell(idx,6,p['assets'])
 if chart_buildings:
  chart=BarChart(); chart.type='col'; chart.style=10; chart.title='Top náklady podľa budovy'; chart.y_axis.title='EUR'; chart.height=7.5; chart.width=13
  chart.add_data(Reference(chart_data,min_col=2,max_col=3,min_row=1,max_row=1+len(chart_buildings)),titles_from_data=True)
  chart.set_categories(Reference(chart_data,min_col=1,min_row=2,max_row=1+len(chart_buildings)))
  chart.legend.position='b'; ws.add_chart(chart,'J4')
 if chart_professions:
  pie=PieChart(); pie.title='Assety podľa profesie'; pie.height=7.5; pie.width=10
  pie.add_data(Reference(chart_data,min_col=6,min_row=1,max_row=1+len(chart_professions)),titles_from_data=True)
  pie.set_categories(Reference(chart_data,min_col=5,min_row=2,max_row=1+len(chart_professions)))
  pie.legend.position='r'; ws.add_chart(pie,'J19')
 for col,width in {'A':13,'B':31,'C':11,'D':16,'E':16,'F':12,'G':16,'H':4}.items(): ws.column_dimensions[col].width=width
 ws.auto_filter.ref=f'A{start_row}:G{end_row}' if buildings else None
 ws.print_title_rows='1:11'; ws.page_setup.orientation='landscape'; ws.page_setup.fitToWidth=1; ws.sheet_properties.pageSetUpPr.fitToPage=True

 def styled_sheet(name,title,headers,rows,formats=None,status_col=None,critical_col=None,table_name=None):
  sh=wb.create_sheet(name); sh.sheet_view.showGridLines=False
  sh.merge_cells(start_row=1,start_column=1,end_row=2,end_column=max(1,len(headers)))
  sh.cell(1,1,title); sh.cell(1,1).font=Font(color=white,bold=True,size=16); sh.cell(1,1).fill=PatternFill('solid',fgColor=brand or dark); sh.cell(1,1).alignment=Alignment(vertical='center')
  for row in sh.iter_rows(min_row=1,max_row=2,min_col=1,max_col=len(headers)):
   for cell in row: cell.fill=PatternFill('solid',fgColor=brand or dark)
  sh.cell(3,1,f"Organizácia: {org['name'] if org else ''} · export {datetime.now().strftime('%d.%m.%Y %H:%M')}")
  sh.cell(3,1).font=Font(color=gray,size=9)
  header_row=5
  for col,hdr in enumerate(headers,1):
   cell=sh.cell(header_row,col,hdr); cell.fill=PatternFill('solid',fgColor=dark); cell.font=Font(color=white,bold=True,size=9); cell.alignment=Alignment(vertical='center',wrap_text=True)
  for ridx,row in enumerate(rows,header_row+1):
   for cidx,val in enumerate(row,1):
    cell=sh.cell(ridx,cidx,excel_safe(val)); cell.border=Border(bottom=thin); cell.alignment=Alignment(vertical='top',wrap_text=True)
   if ridx%2==0:
    for cidx in range(1,len(headers)+1): sh.cell(ridx,cidx).fill=PatternFill('solid',fgColor='FAFBFD')
  if formats:
   for col_idx,fmt in formats.items():
    for ridx in range(header_row+1,header_row+1+len(rows)): sh.cell(ridx,col_idx).number_format=fmt
  if status_col:
   for ridx in range(header_row+1,header_row+1+len(rows)):
    val=str(sh.cell(ridx,status_col).value or '')
    if val in {'Ukončené','Ukončená','Vyriešená','Prevádzka'}: sh.cell(ridx,status_col).fill=PatternFill('solid',fgColor=green)
    elif val in {'Kritická','Havária','Porucha','Mimo prevádzky'}: sh.cell(ridx,status_col).fill=PatternFill('solid',fgColor=red)
    elif val in {'Prebieha','Rieši sa','Pozastavené','Čaká na diel'}: sh.cell(ridx,status_col).fill=PatternFill('solid',fgColor=amber)
  if critical_col:
   for ridx in range(header_row+1,header_row+1+len(rows)):
    val=str(sh.cell(ridx,critical_col).value or '')
    if val=='A': sh.cell(ridx,critical_col).fill=PatternFill('solid',fgColor=red)
    elif val=='B': sh.cell(ridx,critical_col).fill=PatternFill('solid',fgColor=amber)
    elif val=='C': sh.cell(ridx,critical_col).fill=PatternFill('solid',fgColor=green)
  end=max(header_row+1,header_row+len(rows))
  if rows and table_name:
   table=Table(displayName=table_name,ref=f"A{header_row}:{get_column_letter(len(headers))}{end}")
   table.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True,showFirstColumn=False,showLastColumn=False)
   sh.add_table(table)
  sh.freeze_panes=f'A{header_row+1}'; sh.auto_filter.ref=f"A{header_row}:{get_column_letter(len(headers))}{end}" if rows else None
  for cidx,hdr in enumerate(headers,1):
   values=[str(hdr)]+[str(row[cidx-1] or '') for row in rows[:250]]
   width=min(38,max(11,max(len(v) for v in values)+2))
   sh.column_dimensions[get_column_letter(cidx)].width=width
  sh.row_dimensions[1].height=24; sh.page_setup.orientation='landscape'; sh.page_setup.fitToWidth=1; sh.sheet_properties.pageSetUpPr.fitToPage=True
  return sh

 asset_data=[[r[k] for k in ['asset_id','name','building','floor','room','profession','grp','type','manufacturer','model','serial','system_id','status','criticality','purchase_price']] for r in assets_rows]
 styled_sheet('Assety','ASSET REGISTER',['Asset ID','Názov','Budova','Podlažie','Miestnosť','Profesia','Skupina','Typ','Výrobca','Model','Sériové číslo','System ID','Stav','Kritickosť','Cena'],asset_data,{15:money_fmt},13,14,'AssetsTable')

 work_data=[[r['asset_id'],r['asset'],r['building'],r['title'],r['kind'],r['priority'],r['status'],excel_date(r['due']),r['supplier'],r['technician'],r['cost'],r['description']] for r in wo_rows]
 work=styled_sheet('Údržba','ÚDRŽBA & REVÍZIE',['Asset ID','Asset','Budova','Pracovný príkaz','Typ','Priorita','Stav','Termín','Dodávateľ','Technik','Náklad','Popis'],work_data,{8:date_fmt,11:money_fmt},7,None,'MaintenanceTable')
 for ridx in range(6,6+len(work_data)):
  due=work.cell(ridx,8).value
  if due and str(due)[:10]<date.today().isoformat() and str(work.cell(ridx,7).value)!='Ukončené':
   work.cell(ridx,8).fill=PatternFill('solid',fgColor=red); work.cell(ridx,8).font=Font(color='A61B2B',bold=True)

 incident_data=[[r['asset_id'],r['asset'],r['building'],r['title'],r['severity'],r['status'],excel_date(r['reported']),r['impact'],r['cause'],r['cost']] for r in inc_rows]
 incidents_sh=styled_sheet('Incidenty','PORUCHY & HAVÁRIE',['Asset ID','Asset','Budova','Incident','Závažnosť','Stav','Nahlásené','Dopad','Príčina','Náklad'],incident_data,{7:date_fmt,10:money_fmt},6,None,'IncidentsTable')
 for ridx in range(6,6+len(incident_data)):
  sev=str(incidents_sh.cell(ridx,5).value or '')
  incidents_sh.cell(ridx,5).fill=PatternFill('solid',fgColor=red if sev in {'Kritická','Havária','Vysoká'} else amber)

 overdue_data=[[r['asset_id'],r['asset'],r['building'],r['title'],r['priority'],excel_date(r['due']),r['technician'],r['supplier'],r['status']] for r in overdue_rows]
 overdue_sh=styled_sheet('Po termíne','ÚLOHY PO TERMÍNE',['Asset ID','Asset','Budova','Úloha','Priorita','Termín','Technik','Dodávateľ','Stav'],overdue_data,{6:date_fmt},9,None,'OverdueTable')
 for ridx in range(6,6+len(overdue_data)):
  overdue_sh.cell(ridx,6).fill=PatternFill('solid',fgColor=red); overdue_sh.cell(ridx,6).font=Font(color='A61B2B',bold=True)

 stream=io.BytesIO(); wb.save(stream); stream.seek(0)
 audit('REPORT_EXPORT',f'XLSX management report · {len(assets_rows)} assets · {len(wo_rows)} workorders · {len(inc_rows)} incidents')
 code=(org['code'] if org else 'ORG')
 return send_file(stream,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',as_attachment=True,download_name=f'GAMO_report_{code}_{date.today().isoformat()}.xlsx')

@app.route('/buildings')
def buildings(): return render_template('index.html',page='buildings',buildings=q('select b.*,(select count(*) from floors where building_id=b.id) floors,(select count(*) from assets where building_id=b.id) assets from buildings b where b.organization_id=?',(org_id(),)))
@app.route('/building/<int:i>')
def building(i):
 b=one('select * from buildings where id=? and organization_id=?',(i,org_id()))
 if not b: abort(404)
 return render_template('index.html',page='building',b=b,floors=q('select * from floors where building_id=?',(i,)),rooms=q("select r.*,f.code floor,(select count(*) from assets a where a.room_id=r.id) asset_count,(select count(*) from incidents x join assets a on a.id=x.asset_id where a.room_id=r.id and x.status!='Ukončená') incident_count from rooms r join floors f on f.id=r.floor_id where f.building_id=?",(i,)),assets=q('select a.*,r.code room from assets a left join rooms r on r.id=a.room_id where a.building_id=?',(i,)),documents=q('select id,name,category,mime,size,uploaded from documents where building_id=? order by id desc',(i,)))
@app.post('/building/<int:i>/document')
def upload_building_document(i):
 if not owns_building(i): abort(404)
 f=request.files.get('document'); category=(request.form.get('category') or 'Technická').strip()
 if not f or not f.filename:
  flash('Vyber dokument na nahratie.','error'); return redirect(f'/building/{i}#documents')
 allowed={'.pdf','.doc','.docx','.xls','.xlsx','.jpg','.jpeg','.png','.txt'}; ext=os.path.splitext(f.filename)[1].lower()
 if ext not in allowed:
  flash('Nepodporovaný typ súboru.','error'); return redirect(f'/building/{i}#documents')
 data=f.read()
 x('insert into documents(building_id,name,category,mime,size,data) values(?,?,?,?,?,?)',(i,os.path.basename(f.filename),category,f.mimetype or 'application/octet-stream',len(data),data))
 audit('DOCUMENT_UPLOAD',f.filename); flash('Dokument bol nahratý.','success'); return redirect(f'/building/{i}#documents')

@app.get('/document/<int:i>/download')
def download_document(i):
 d=one('select d.* from documents d join buildings b on b.id=d.building_id where d.id=? and b.organization_id=?',(i,org_id()))
 if not d: abort(404)
 return send_file(io.BytesIO(d['data']),mimetype=d['mime'] or 'application/octet-stream',as_attachment=True,download_name=d['name'])

@app.post('/document/<int:i>/delete')
def delete_document(i):
 d=one('select d.building_id,d.name from documents d join buildings b on b.id=d.building_id where d.id=? and b.organization_id=?',(i,org_id()))
 if not d: abort(404)
 x('delete from documents where id=?',(i,)); audit('DOCUMENT_DELETE',d['name']); flash('Dokument bol odstránený.','success')
 return redirect(f"/building/{d['building_id']}#documents")

@app.route('/assets')
def assets(): return render_template('index.html',page='assets',assets=q('select a.*,b.code building,r.code room from assets a join buildings b on b.id=a.building_id left join rooms r on r.id=a.room_id where b.organization_id=? order by a.asset_id',(org_id(),)))
@app.route('/asset/<int:i>')
def asset(i):
 a=one('select a.*,b.name building,f.code floor,r.code room,r.name room_name,r.area from assets a join buildings b on b.id=a.building_id left join floors f on f.id=a.floor_id left join rooms r on r.id=a.room_id where a.id=? and b.organization_id=?',(i,org_id()))
 if not a: abort(404)
 children=q("""select a.*,r.code room,r.name room_name,r.area from assets a
  join buildings b on b.id=a.building_id left join rooms r on r.id=a.room_id
  where a.parent_id=? and b.organization_id=? order by a.asset_id""",(i,org_id()))
 parent=one("""select a.id,a.asset_id,a.name,a.status from assets a join buildings b on b.id=a.building_id
  where a.id=? and b.organization_id=?""",(a['parent_id'],org_id())) if a['parent_id'] else None
 impact_rooms=len({x['room'] for x in children if x['room']}); impact_area=sum(float(x['area'] or 0) for x in children if x['room'])
 orders=q("""select w.* from workorders w join assets aa on aa.id=w.asset_id join buildings b on b.id=aa.building_id
  where w.asset_id=? and b.organization_id=? order by w.id desc""",(i,org_id()))
 incidents=q("""select x.* from incidents x join assets aa on aa.id=x.asset_id join buildings b on b.id=aa.building_id
  where x.asset_id=? and b.organization_id=? order by x.id desc""",(i,org_id()))
 events=q('select * from asset_events where asset_id=? and organization_id=? order by id desc limit 100',(i,org_id()))
 return render_template('index.html',page='asset',a=a,parent=parent,children=children,impact_rooms=impact_rooms,impact_area=impact_area,orders=orders,incidents=incidents,events=events)
@app.route('/maintenance')
def maintenance(): return render_template('index.html',page='maintenance',orders=q('select w.*,a.asset_id,a.name asset from workorders w join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id where b.organization_id=? order by w.id desc',(org_id(),)))
@app.route('/incidents')
def incidents(): return render_template('index.html',page='incidents',incidents=q('select i.*,a.asset_id,a.name asset from incidents i join assets a on a.id=i.asset_id join buildings b on b.id=a.building_id where b.organization_id=? order by i.id desc',(org_id(),)))
@app.route('/admin')
def admin():
 org=one('select * from organizations where id=?',(org_id(),))
 organizations=[]; customer_stats={'total':0,'active':0,'paused':0,'users':0,'buildings':0}
 if is_gamo_admin():
  organizations=q_system("""select o.*,
   (select count(*) from users u where u.organization_id=o.id) users_count,
   (select count(*) from buildings b where b.organization_id=o.id) buildings_count,
   (select u.name from users u where u.organization_id=o.id and u.role='Administrator' order by u.id limit 1) admin_name,
   (select u.email from users u where u.organization_id=o.id and u.role='Administrator' order by u.id limit 1) admin_email,
   (select u.last_login from users u where u.organization_id=o.id and u.role='Administrator' order by u.id limit 1) admin_last_login
   from organizations o where o.code<>'GAMO' order by o.name""")
  active_customers=sum(1 for o in organizations if o['status']=='Aktívny' and o['license_status']=='Aktívna' and (not o['license_until'] or str(o['license_until'])[:10]>=date.today().isoformat()))
  customer_stats={
   'total':len(organizations),
   'active':active_customers,
   'paused':len(organizations)-active_customers,
   'users':sum(int(o['users_count'] or 0) for o in organizations),
   'buildings':sum(int(o['buildings_count'] or 0) for o in organizations)
  }
 audit_rows=q('select * from audit_log where organization_id=? order by id desc limit 20',(org_id(),))
 return render_template('index.html',page='admin',
  users=q('select * from users where organization_id=? order by name',(org_id(),)),
  buildings=q('select * from buildings where organization_id=? order by name',(org_id(),)),
  audit_rows=audit_rows,organizations=organizations,customer_stats=customer_stats,current_admin_org=org)

@app.get('/privacy')
def privacy_center():
 if support_mode(): abort(403)
 org=one('select * from organizations where id=?',(org_id(),))
 if not org or session.get('user_role')!='Administrator': abort(403)
 access_rows=q('select * from customer_access_log where target_organization_id=? order by id desc limit 50',(org_id(),))
 return render_template('index.html',page='privacy',privacy_org=org,support_active=support_access_active(org),access_rows=access_rows,rls_enabled=USING_POSTGRES)

@app.post('/privacy/settings')
def privacy_settings():
 if support_mode(): abort(403)
 org=one('select * from organizations where id=?',(org_id(),))
 if not org or session.get('user_role')!='Administrator': abort(403)
 contact=(request.form.get('privacy_contact') or '').strip()[:160]
 try: retention=max(30,min(3650,int(request.form.get('retention_days') or 3650)))
 except (TypeError,ValueError): retention=3650
 x('update organizations set privacy_contact=?,retention_days=? where id=?',(contact,retention,org_id()))
 audit('PRIVACY_SETTINGS',f'retention={retention}')
 flash('Nastavenia súkromia boli uložené.','success')
 return redirect('/privacy')

@app.post('/privacy/support-access')
def privacy_support_access():
 if support_mode(): abort(403)
 org=one('select * from organizations where id=?',(org_id(),))
 if not org or org['code']=='GAMO' or session.get('user_role')!='Administrator': abort(403)
 action=request.form.get('action')
 reason=(request.form.get('reason') or '').strip()[:500]
 if action=='revoke':
  x('update organizations set support_access_enabled=?,support_access_until=? where id=?',(False if USING_POSTGRES else 0,None,org_id()))
  customer_access(org_id(),'SUPPORT_ACCESS_REVOKED',reason or 'Prístup GAMO bol odvolaný zákazníkom.')
  audit('SUPPORT_ACCESS_REVOKED',reason)
  flash('Prístup GAMO k zákazníckym dátam bol okamžite odvolaný.','success')
 else:
  try: hours=int(request.form.get('hours') or 24)
  except (TypeError,ValueError): hours=24
  if hours not in {1,24,168}: hours=24
  until=(datetime.utcnow()+timedelta(hours=hours)).isoformat(timespec='seconds')+'Z'
  x('update organizations set support_access_enabled=?,support_access_until=? where id=?',(True if USING_POSTGRES else 1,until,org_id()))
  customer_access(org_id(),'SUPPORT_ACCESS_GRANTED',reason or f'Dočasný prístup na {hours} h.')
  audit('SUPPORT_ACCESS_GRANTED',f'{hours}h · {reason}')
  flash(f'GAMO support má dočasný prístup na {hours} hodín.','success')
 return redirect('/privacy')

@app.get('/backup/my')
def backup_my_organization():
 if support_mode(): abort(403)
 if session.get('user_role')!='Administrator': abort(403)
 customer_access(org_id(),'CUSTOMER_DATA_EXPORT','Export vytvorený administrátorom organizácie.')
 return build_organization_backup(org_id())

@app.post('/platform/customer/<int:i>/support-enter')
def platform_customer_support_enter(i):
 if not is_gamo_admin(): abort(403)
 customer=one_system('select * from organizations where id=? and code<>?',(i,'GAMO'))
 if not customer: abort(404)
 if not support_access_active(customer):
  flash('Zákazník nemá aktívny dočasný support prístup.','error')
  return redirect(f'/platform/customer/{i}')
 session['support_target_org_id']=customer['id']
 session['support_target_name']=customer['name']
 session['support_target_code']=customer['code']
 customer_access(i,'GAMO_SUPPORT_SESSION_ENTER','GAMO vstúpilo do auditovaného support režimu zákazníka.')
 audit('SUPPORT_SESSION_ENTER',f"{customer['code']} · {customer['name']}")
 return redirect('/')

@app.post('/support/exit')
def support_exit():
 target_id=session.get('support_target_org_id')
 if not target_id: return redirect('/')
 customer=one_system('select id,code,name from organizations where id=?',(target_id,))
 if customer:
  customer_access(target_id,'GAMO_SUPPORT_SESSION_EXIT','GAMO ukončilo auditovaný support režim.')
  audit('SUPPORT_SESSION_EXIT',f"{customer['code']} · {customer['name']}")
 session.pop('support_target_org_id',None); session.pop('support_target_name',None); session.pop('support_target_code',None)
 return redirect(f'/platform/customer/{target_id}' if customer else '/admin')

@app.get('/platform/customer/<int:i>/backup')
def platform_customer_backup(i):
 if not is_gamo_admin(): abort(403)
 customer=one_system('select * from organizations where id=? and code<>?',(i,'GAMO'))
 if not customer: abort(404)
 if not support_access_active(customer):
  flash('Zákazník nemá aktívny súhlas na prístup GAMO k dátam. Backup nie je dostupný.','error')
  return redirect(f'/platform/customer/{i}')
 customer_access(i,'GAMO_BACKUP_EXPORT','GAMO administrátor stiahol zákaznícky export počas aktívneho support prístupu.')
 return build_organization_backup(i,privileged=True)

def build_organization_backup(oid,privileged=False):
 read_one=one_system if privileged else one
 read_all=q_system if privileged else q
 org=read_one('select * from organizations where id=?',(oid,))
 if not org: abort(404)
 data={}
 data['buildings']=[dict(r) for r in read_all('select * from buildings where organization_id=? order by id',(oid,))]
 data['floors']=[dict(r) for r in read_all('select f.* from floors f join buildings b on b.id=f.building_id where b.organization_id=? order by f.id',(oid,))]
 data['rooms']=[dict(r) for r in read_all('select r.* from rooms r join floors f on f.id=r.floor_id join buildings b on b.id=f.building_id where b.organization_id=? order by r.id',(oid,))]
 data['assets']=[dict(r) for r in read_all('select a.* from assets a where a.organization_id=? order by a.id',(oid,))]
 data['workorders']=[dict(r) for r in read_all('select w.* from workorders w join assets a on a.id=w.asset_id where a.organization_id=? order by w.id',(oid,))]
 data['incidents']=[dict(r) for r in read_all('select x.* from incidents x join assets a on a.id=x.asset_id where a.organization_id=? order by x.id',(oid,))]
 data['users']=[dict(r) for r in read_all('select id,name,email,role,status,last_login,organization_id from users where organization_id=? order by id',(oid,))]
 data['settings']=[dict(r) for r in read_all('select k,v from organization_settings where organization_id=? order by k',(oid,))]
 data['asset_events']=[dict(r) for r in read_all('select * from asset_events where organization_id=? order by id',(oid,))]
 data['access_log']=[dict(r) for r in read_all('select * from customer_access_log where target_organization_id=? order by id',(oid,))]
 docs=read_all('select id,building_id,name,category,mime,size,uploaded,data from documents where building_id in (select id from buildings where organization_id=?) order by id',(oid,))
 manifest={
  'format':'GAMO_ORGANIZATION_BACKUP_V2','generated_at':datetime.utcnow().isoformat(timespec='seconds')+'Z',
  'organization':{k:org[k] for k in ['id','code','name','status','plan','license_status','license_until','branding_name','brand_color','brand_tagline','privacy_contact','data_region','retention_days','created'] if k in org.keys()},
  'privacy':{'password_hashes_included':False,'support_access_active':support_access_active(org)},
  'note':'Password hashes are intentionally excluded. Documents are stored in the documents/ folder.'
 }
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2,default=str))
  for name,rows in data.items():
   z.writestr(f'data/{name}.json',json.dumps(rows,ensure_ascii=False,indent=2,default=str))
  doc_meta=[]
  for d in docs:
   item={k:d[k] for k in ['id','building_id','name','category','mime','size','uploaded']}
   safe=os.path.basename(d['name'] or f"document_{d['id']}")
   path=f"documents/{d['id']}_{safe}"
   item['archive_path']=path; doc_meta.append(item)
   z.writestr(path,bytes(d['data']) if d['data'] is not None else b'')
  z.writestr('data/documents.json',json.dumps(doc_meta,ensure_ascii=False,indent=2,default=str))
 stream.seek(0)
 audit('BACKUP_EXPORT',f"{org['code']} · organization export")
 filename=f"GAMO_backup_{org['code']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
 return send_file(stream,mimetype='application/zip',as_attachment=True,download_name=filename)

@app.get('/platform/customer/<int:i>')
def platform_customer_detail(i):
 if not is_gamo_admin(): abort(403)
 customer=one_system('select * from organizations where id=? and code<>?',(i,'GAMO'))
 if not customer: abort(404)
 support_active=support_access_active(customer)
 customer_access(i,'GAMO_METADATA_VIEW','GAMO otvorilo licenčné a agregované metadáta zákazníka.')
 customer_stats={
  'users':one_system('select count(*) n from users where organization_id=?',(i,))['n'],
  'active_users':one_system("select count(*) n from users where organization_id=? and status='Aktívny'",(i,))['n'],
  'buildings':one_system('select count(*) n from buildings where organization_id=?',(i,))['n'],
  'assets':one_system('select count(*) n from assets where organization_id=?',(i,))['n'],
  'open_incidents':one_system("select count(*) n from incidents x join assets a on a.id=x.asset_id where a.organization_id=? and x.status!='Ukončená'",(i,))['n'],
  'open_orders':one_system("select count(*) n from workorders w join assets a on a.id=w.asset_id where a.organization_id=? and w.status!='Ukončené'",(i,))['n'],
  'maintenance_cost':one_system('select coalesce(sum(w.cost),0) n from workorders w join assets a on a.id=w.asset_id where a.organization_id=?',(i,))['n'],
  'incident_cost':one_system('select coalesce(sum(x.cost),0) n from incidents x join assets a on a.id=x.asset_id where a.organization_id=?',(i,))['n']
 }
 customer_stats['total_cost']=customer_stats['maintenance_cost']+customer_stats['incident_cost']
 license_days=None
 if customer['license_until']:
  try: license_days=(datetime.strptime(str(customer['license_until'])[:10],'%Y-%m-%d').date()-date.today()).days
  except Exception: license_days=None
 customer_users=[]; customer_buildings=[]; recent_incidents=[]; recent_orders=[]; customer_audit=[]
 if support_active:
  customer_access(i,'GAMO_SUPPORT_DATA_VIEW','Customer 360 sensitive data viewed during active support access.')
  customer_users=q_system('select id,name,email,role,status,last_login from users where organization_id=? order by case when role=\'Administrator\' then 0 else 1 end,name',(i,))
  customer_buildings=q_system("""select b.*,
   (select count(*) from floors f where f.building_id=b.id) floors_count,
   (select count(*) from assets a where a.building_id=b.id) assets_count,
   (select count(*) from incidents x join assets a on a.id=x.asset_id where a.building_id=b.id and x.status!='Ukončená') incidents_count
   from buildings b where b.organization_id=? order by b.name""",(i,))
  recent_incidents=q_system("""select x.*,a.asset_id,a.name asset,b.name building from incidents x
   join assets a on a.id=x.asset_id join buildings b on b.id=a.building_id
   where a.organization_id=? order by x.id desc limit 6""",(i,))
  recent_orders=q_system("""select w.*,a.asset_id,a.name asset,b.name building from workorders w
   join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id
   where a.organization_id=? order by w.id desc limit 6""",(i,))
  customer_audit=q_system('select * from audit_log where organization_id=? order by id desc limit 10',(i,))
 last_backup=one_system("select created from audit_log where organization_id=? and action='BACKUP_EXPORT' order by id desc limit 1",(i,))
 last_login=one_system("select max(last_login) last_login from users where organization_id=?",(i,))
 access_rows=q_system('select * from customer_access_log where target_organization_id=? order by id desc limit 20',(i,))
 limits=PLAN_LIMITS.get((customer['plan'] or 'BASIC'),PLAN_LIMITS['BASIC'])
 return render_template('index.html',page='customer',customer=customer,customer_stats=customer_stats,
  customer_users=customer_users,customer_buildings=customer_buildings,recent_incidents=recent_incidents,
  recent_orders=recent_orders,license_days=license_days,customer_limits=limits,customer_audit=customer_audit,
  customer_last_backup=(last_backup['created'] if last_backup else None),customer_last_login=(last_login['last_login'] if last_login else None),
  support_access=support_active,customer_access_rows=access_rows)

@app.post('/platform/customer/<int:i>/reset-admin-password')
def platform_customer_reset_admin_password(i):
 if not is_gamo_admin(): abort(403)
 customer=one_system('select * from organizations where id=? and code<>?',(i,'GAMO'))
 if not customer: abort(404)
 if not support_access_active(customer):
  flash('Reset hesla vyžaduje aktívny support prístup udelený zákazníkom.','error')
  return redirect(f'/platform/customer/{i}#customerUsers')
 password=request.form.get('password') or ''
 if len(password)<8:
  flash('Dočasné heslo musí mať aspoň 8 znakov.','error'); return redirect(f'/platform/customer/{i}#customerUsers')
 admin_user=one_system("select id,name,email from users where organization_id=? and role='Administrator' order by id limit 1",(i,))
 if not admin_user:
  flash('Zákazník nemá administrátorský účet.','error'); return redirect(f'/platform/customer/{i}#customerUsers')
 x_system('update users set password_hash=?,status=? where id=?',(generate_password_hash(password),'Aktívny',admin_user['id']))
 customer_access(i,'GAMO_ADMIN_PASSWORD_RESET',f"Reset hesla administrátora {admin_user['email']}.")
 audit('CUSTOMER_ADMIN_PASSWORD_RESET',f"{customer['code']} · {admin_user['email']}")
 flash('Dočasné heslo zákazníckeho administrátora bolo zmenené.','success')
 return redirect(f'/platform/customer/{i}#customerUsers')

@app.post('/platform/customer/<int:i>/branding')
def platform_customer_branding(i):
 if not is_gamo_admin(): abort(403)
 customer=one_system('select * from organizations where id=? and code<>?',(i,'GAMO'))
 if not customer: abort(404)
 name=(request.form.get('branding_name') or customer['name']).strip()[:80]
 tagline=(request.form.get('brand_tagline') or 'FACILITY MANAGEMENT').strip()[:80]
 color=(request.form.get('brand_color') or '#E31B23').strip().upper()
 if len(color)!=7 or not color.startswith('#') or any(ch not in '0123456789ABCDEF' for ch in color[1:]):
  flash('Farba brandingu musí byť vo formáte #RRGGBB.','error'); return redirect(f'/platform/customer/{i}#branding')
 x_system('update organizations set branding_name=?,brand_color=?,brand_tagline=? where id=?',(name,color,tagline,i))
 audit('CUSTOMER_BRANDING',f"{customer['code']} · {name} · {color}")
 flash('Branding zákazníka bol uložený.','success')
 return redirect(f'/platform/customer/{i}#branding')

@app.post('/platform/customer')
def platform_customer():
 if not is_gamo_admin(): abort(403)
 f=request.form
 code=(f.get('code') or '').strip().upper()
 name=(f.get('name') or '').strip()
 admin_name=(f.get('admin_name') or '').strip()
 email=(f.get('email') or '').strip().lower()
 password=f.get('password') or ''
 plan=(f.get('plan') or 'BUSINESS').upper()
 license_status=f.get('license_status') or 'Aktívna'
 license_until=(f.get('license_until') or '').strip() or None
 if not code or not name or not admin_name or not email or len(password)<8:
  flash('Vyplň povinné údaje. Dočasné heslo musí mať aspoň 8 znakov.','error'); return redirect('/admin#customersAdmin')
 if plan not in {'BASIC','BUSINESS','ENTERPRISE'} or license_status not in {'Aktívna','Pozastavená'}:
  flash('Neplatný licenčný plán alebo stav.','error'); return redirect('/admin#customersAdmin')
 if one_system('select id from organizations where upper(code)=?',(code,)) or one_system('select id from users where lower(email)=?',(email,)):
  flash('Kód zákazníka alebo e-mail administrátora už existuje.','error'); return redirect('/admin#customersAdmin')
 try:
  with con(system=True) as db:
   if USING_POSTGRES:
    row=db.execute(_sql('insert into organizations(code,name,status,plan,license_status,license_until,branding_name,privacy_contact) values(?,?,?,?,?,?,?,?) returning id'),(code,name,'Aktívny',plan,license_status,license_until,name,email)).fetchone()
    oid=row['id']
   else:
    cur=db.execute(_sql('insert into organizations(code,name,status,plan,license_status,license_until,branding_name,privacy_contact) values(?,?,?,?,?,?,?,?)'),(code,name,'Aktívny',plan,license_status,license_until,name,email)); oid=cur.lastrowid
   db.execute(_sql('insert into users(name,email,role,status,password_hash,organization_id) values(?,?,?,?,?,?)'),(admin_name,email,'Administrator','Aktívny',generate_password_hash(password),oid))
   db.commit()
  audit('CUSTOMER_CREATE',f'{code} · {name} · {plan}')
  flash('Zákazník bol vytvorený. Má vlastnú organizáciu a administrátorský účet.','success')
 except Exception:
  flash('Zákazníka sa nepodarilo vytvoriť. Neboli uložené neúplné dáta.','error')
 return redirect('/admin#customersAdmin')

@app.post('/platform/customer/<int:i>/update')
def platform_customer_update(i):
 if not is_gamo_admin(): abort(403)
 customer=one_system('select * from organizations where id=?',(i,))
 if not customer or customer['code']=='GAMO': abort(404)
 f=request.form
 plan=(f.get('plan') or customer['plan']).upper()
 license_status=f.get('license_status') or customer['license_status']
 org_status=f.get('status') or customer['status']
 license_until=(f.get('license_until') or '').strip() or None
 if plan not in {'BASIC','BUSINESS','ENTERPRISE'} or license_status not in {'Aktívna','Pozastavená'} or org_status not in {'Aktívny','Neaktívny'}:
  abort(400)
 x_system('update organizations set plan=?,license_status=?,license_until=?,status=? where id=?',(plan,license_status,license_until,org_status,i))
 audit('CUSTOMER_UPDATE',f"{customer['code']} · {plan} · {license_status}")
 flash('Nastavenia zákazníka boli uložené.','success')
 return redirect(f"/platform/customer/{i}" if request.form.get('return_to')=='detail' else '/admin#customersAdmin')

@app.route('/add/<what>',methods=['GET','POST'])
def add(what):
 if request.method=='GET':
  return redirect({'incident':'/incidents','workorder':'/maintenance','asset':'/assets','user':'/admin','building':'/buildings'}.get(what,'/'))
 f=request.form
 try:
  if what=='building':
   if not plan_allows('buildings'):
    flash('Licenčný limit počtu budov bol dosiahnutý. GAMO môže upraviť licenčný plán.','error'); return redirect('/buildings')
   code=f.get('code','').strip().upper(); name=f.get('name','').strip()
   try: floor_count=max(0,min(50,int(f.get('floors_count') or 0)))
   except (TypeError,ValueError): raise ValueError()
   if not code or not name: flash('Kód a názov budovy sú povinné.','error')
   elif one('select id from buildings where upper(code)=? and organization_id=?',(code,org_id())): flash(f'Budova s kódom {code} už existuje.','error')
   else:
    owner=one('select name from organizations where id=?',(org_id(),))
    customer_name=(owner['name'] if owner else 'GAMO a.s.')
    bid=x('insert into buildings(code,name,address,manager,customer,organization_id) values(?,?,?,?,?,?)',(code,name,f.get('address','').strip(),f.get('manager','').strip(),customer_name,org_id()))
    for n in range(1,floor_count+1): x('insert into floors(building_id,code,name) values(?,?,?)',(bid,f'{n}.NP',f'{n}. nadzemné podlažie'))
    audit('BUILDING_CREATE',f'{name} · {floor_count} podlaží'); flash('Budova a jej základná 3D štruktúra boli vytvorené.','success')
  elif what=='floor':
   building_id=f.get('building_id'); code=(f.get('code') or '').strip().upper(); name=(f.get('name') or '').strip()
   if not owns_building(building_id): abort(404)
   if not code or not name or one('select id from floors where building_id=? and upper(code)=?',(building_id,code)): raise ValueError()
   x('insert into floors(building_id,code,name) values(?,?,?)',(building_id,code,name)); audit('FLOOR_CREATE',f'{code} · {name}'); flash('Podlažie bolo pridané.','success')
  elif what=='room':
   floor_id=f.get('floor_id'); code=(f.get('code') or '').strip().upper(); name=(f.get('name') or '').strip()
   floor=one('select f.id from floors f join buildings b on b.id=f.building_id where f.id=? and b.organization_id=?',(floor_id,org_id()))
   if not floor: abort(404)
   if not code or not name or one('select id from rooms where floor_id=? and upper(code)=?',(floor_id,code)): raise ValueError()
   try: area=max(0,float(f.get('area') or 0))
   except (TypeError,ValueError): raise ValueError()
   x('insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)',(floor_id,code,name,area,f.get('tenant','').strip(),f.get('zone','').strip())); audit('ROOM_CREATE',f'{code} · {name}'); flash('Miestnosť bola pridaná.','success')
  elif what=='asset':
   if not plan_allows('assets'):
    flash('Licenčný limit počtu assetov bol dosiahnutý. GAMO môže upraviť licenčný plán.','error'); return redirect('/assets')
   aid=f.get('asset_id','').strip().upper(); name=(f.get('name') or '').strip(); building_id=f.get('building_id')
   floor_id=f.get('floor_id'); room_id=f.get('room_id'); parent_id=f.get('parent_id')
   profession=(f.get('profession') or '').strip(); grp=(f.get('grp') or '').strip(); asset_type=(f.get('type') or '').strip()
   if not aid or not name or not building_id or not floor_id or not room_id or not profession or not grp or not asset_type: raise ValueError()
   if not owns_building(building_id): abort(404)
   if floor_id and not one('select f.id from floors f join buildings b on b.id=f.building_id where f.id=? and b.id=? and b.organization_id=?',(floor_id,building_id,org_id())): raise ValueError()
   if room_id and (not floor_id or not one('select r.id from rooms r join floors f on f.id=r.floor_id join buildings b on b.id=f.building_id where r.id=? and r.floor_id=? and b.id=? and b.organization_id=?',(room_id,floor_id,building_id,org_id()))): raise ValueError()
   if parent_id and not owns_asset(parent_id): raise ValueError()
   if one('select a.id from assets a join buildings b on b.id=a.building_id where upper(a.asset_id)=? and b.organization_id=?',(aid,org_id())): flash(f'Asset ID {aid} už existuje.','error')
   else:
    values=tuple((aid if k=='asset_id' else f.get(k)) or None for k in ['asset_id','name','building_id','floor_id','room_id','profession','grp','type','manufacturer','model','serial','system_id','parent_id','status','criticality','service_months','revision_months','purchase_price','ip','protocol','notes'])
    new_asset=x('insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,serial,system_id,parent_id,status,criticality,service_months,revision_months,purchase_price,ip,protocol,notes,organization_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',values+(org_id(),))
    asset_event(new_asset,'ASSET_CREATE','Asset vytvorený',f"{aid} · {f.get('name','')}")
    flash('Asset bol vytvorený.','success')
  elif what=='workorder':
   allowed_priority={'Nízka','Stredná','Vysoká','Kritická'}; allowed_status={'Plánované','Pridelené','Prebieha','Pozastavené','Ukončené','Zrušené'}; allowed_kind={'PM','REV','OPR','VYM'}
   if not (f.get('title') or '').strip() or f.get('priority') not in allowed_priority or f.get('status') not in allowed_status or f.get('kind') not in allowed_kind or not owns_asset(f.get('asset_id')): raise ValueError()
   x('insert into workorders(asset_id,title,kind,priority,status,due,supplier,technician,cost,description) values(?,?,?,?,?,?,?,?,?,?)',tuple(f.get(k,'') for k in ['asset_id','title','kind','priority','status','due','supplier','technician','cost','description']))
   asset_event(f.get('asset_id'),'WORKORDER_CREATE','Nový pracovný príkaz',f"{f.get('kind','')} · {f.get('title','')}")
   audit('WORKORDER_CREATE',f.get('title','')); flash('Pracovný príkaz bol vytvorený.','success')
  elif what=='incident':
   allowed_severity={'Nízka','Stredná','Vysoká','Kritická','Havária'}; allowed_status={'Otvorená','Pridelená','Rieši sa','Čaká na diel','Vyriešená','Ukončená'}
   if not (f.get('title') or '').strip() or f.get('severity') not in allowed_severity or f.get('status') not in allowed_status or not owns_asset(f.get('asset_id')): raise ValueError()
   x('insert into incidents(asset_id,title,severity,status,reported,impact,cause,cost) values(?,?,?,?,?,?,?,?)',tuple(f.get(k,'') for k in ['asset_id','title','severity','status','reported','impact','cause','cost']))
   asset_event(f.get('asset_id'),'INCIDENT_CREATE','Incident zaevidovaný',f"{f.get('severity','')} · {f.get('title','')}")
   audit('INCIDENT_CREATE',f.get('title','')); flash('Incident bol zaevidovaný.','success')
  elif what=='user':
   if not plan_allows('users'):
    flash('Licenčný limit používateľov bol dosiahnutý. GAMO môže upraviť licenčný plán.','error'); return redirect('/admin#usersAdmin')
   name=(f.get('name') or '').strip(); email=(f.get('email') or '').strip().lower(); pwd=f.get('password') or ''
   role=f.get('role') or 'Viewer'; status=f.get('status') or 'Aktívny'
   if not name or not email or len(pwd)<8 or role not in {'Administrator','Facility Manager','Technik','Servisný technik','Viewer'} or status not in {'Aktívny','Neaktívny'}: raise ValueError()
   if one('select id from users where lower(email)=?',(email,)): raise IntegrityError()
   x('insert into users(name,email,role,status,password_hash,organization_id) values(?,?,?,?,?,?)',(name,email,role,status,generate_password_hash(pwd),org_id()))
   audit('USER_CREATE',f'{name} · {role}'); flash('Používateľ bol vytvorený.','success')
 except (IntegrityError,ValueError):
  flash('Záznam sa nepodarilo uložiť. Skontroluj duplicity a zadané hodnoty.','error')
 except Exception:
  flash('Pri ukladaní nastala chyba. Dáta neboli poškodené.','error')
 target={'incident':'/incidents','workorder':'/maintenance','asset':'/assets','user':'/admin','building':'/buildings'}.get(what)
 return redirect(target or request.referrer or '/')
@app.post('/user/<int:i>/update')
def update_user(i):
 f=request.form
 u=one('select * from users where id=? and organization_id=?',(i,org_id()))
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
 ownership={
  'building':owns_building,'floor':owns_floor,'room':owns_room,'asset':owns_asset,
  'workorder':owns_workorder,'incident':owns_incident,'user':owns_user
 }
 if what not in ownership: abort(404)
 if not ownership[what](i): abort(404)
 if what=='building':
  if one('select id from assets where building_id=? limit 1',(i,)):
   flash('Budovu nie je možné odstrániť, kým obsahuje assety.','error'); return redirect(request.referrer or '/buildings')
  x('delete from buildings where id=?',(i,)); audit('BUILDING_DELETE',str(i))
 elif what=='floor':
  if one('select id from assets where floor_id=? limit 1',(i,)):
   flash('Podlažie nie je možné odstrániť, kým obsahuje assety.','error'); return redirect(request.referrer or '/buildings')
  x('delete from floors where id=?',(i,)); audit('FLOOR_DELETE',str(i))
 elif what=='room':
  if one('select id from assets where room_id=? limit 1',(i,)):
   flash('Miestnosť nie je možné odstrániť, kým obsahuje assety.','error'); return redirect(request.referrer or '/buildings')
  x('delete from rooms where id=?',(i,)); audit('ROOM_DELETE',str(i))
 elif what=='asset':
  if one('select id from assets where parent_id=? limit 1',(i,)) or one('select id from workorders where asset_id=? limit 1',(i,)) or one('select id from incidents where asset_id=? limit 1',(i,)):
   flash('Asset nie je možné odstrániť, kým má podriadené assety, servisnú históriu alebo incidenty.','error'); return redirect(request.referrer or '/assets')
  x('delete from assets where id=?',(i,)); audit('ASSET_DELETE',str(i))
 elif what=='workorder':
  row=one('select asset_id,title from workorders where id=?',(i,))
  x('delete from workorders where id=?',(i,))
  if row: asset_event(row['asset_id'],'WORKORDER_DELETE','Pracovný príkaz odstránený',row['title'] or '')
  audit('WORKORDER_DELETE',str(i))
 elif what=='incident':
  row=one('select asset_id,title from incidents where id=?',(i,))
  x('delete from incidents where id=?',(i,))
  if row: asset_event(row['asset_id'],'INCIDENT_DELETE','Incident odstránený',row['title'] or '')
  audit('INCIDENT_DELETE',str(i))
 elif what=='user':
  if i==session.get('user_id'):
   flash('Aktuálne prihlásený účet nie je možné odstrániť.','error'); return redirect('/admin#usersAdmin')
  u=one('select role,name from users where id=?',(i,))
  if u and u['role']=='Administrator' and one("select count(*) n from users where organization_id=? and role='Administrator' and status='Aktívny'",(org_id(),))['n']<=1:
   flash('Posledného aktívneho administrátora organizácie nie je možné odstrániť.','error'); return redirect('/admin#usersAdmin')
  x('delete from users where id=?',(i,)); audit('USER_DELETE',u['name'] if u else str(i))
 flash('Záznam bol bezpečne odstránený.','success')
 return redirect(request.referrer or '/')

@app.post('/status/<what>/<int:i>')
def status(what,i):
 allowed={
  'asset':({'Prevádzka','Mimo prevádzky','Servis','Porucha','Vyradené'},owns_asset),
  'workorder':({'Plánované','Pridelené','Prebieha','Pozastavené','Ukončené','Zrušené'},owns_workorder),
  'incident':({'Otvorená','Pridelená','Rieši sa','Čaká na diel','Vyriešená','Ukončená'},owns_incident)
 }
 if what not in allowed: abort(404)
 statuses,owner_check=allowed[what]
 if not owner_check(i): abort(404)
 new_status=request.form.get('status')
 if new_status not in statuses: abort(400)
 if what=='asset':
  x('update assets set status=? where id=?',(new_status,i)); asset_event(i,'STATUS_CHANGE','Zmena stavu assetu',new_status)
 elif what=='workorder':
  row=one('select asset_id,title from workorders where id=?',(i,)); x('update workorders set status=? where id=?',(new_status,i))
  if row: asset_event(row['asset_id'],'WORKORDER_STATUS','Zmena stavu pracovného príkazu',f"{row['title']} → {new_status}")
 else:
  row=one('select asset_id,title from incidents where id=?',(i,)); x('update incidents set status=? where id=?',(new_status,i))
  if row: asset_event(row['asset_id'],'INCIDENT_STATUS','Zmena stavu incidentu',f"{row['title']} → {new_status}")
 audit('STATUS_CHANGE',f'{what}:{i} → {new_status}')
 return redirect(request.referrer or '/')

@app.get('/api/buildings/options')
def api_building_options():
 rows=q('select id,code,name,address from buildings where organization_id=? order by name',(org_id(),))
 return jsonify([dict(r) for r in rows])

@app.get('/api/floors/options')
def api_floor_options():
 rows=q("""select f.id,f.code,f.name,b.id building_id,b.code building_code,b.name building_name
  from floors f join buildings b on b.id=f.building_id
  where b.organization_id=? order by b.name,f.id""",(org_id(),))
 return jsonify([dict(r) for r in rows])

@app.route('/api/floors/<int:b>')
def api_floors(b):
 if not owns_building(b): abort(404)
 return jsonify([dict(r) for r in q('select * from floors where building_id=? order by id',(b,))])

@app.route('/api/rooms/<int:f>')
def api_rooms(f):
 if not owns_floor(f): abort(404)
 return jsonify([dict(r) for r in q('select * from rooms where floor_id=? order by id',(f,))])

@app.get('/api/assets/options')
def api_asset_options():
 rows=q("""select a.id,a.asset_id,a.name,a.profession,b.code building,r.code room
  from assets a join buildings b on b.id=a.building_id
  left join rooms r on r.id=a.room_id
  where b.organization_id=? order by a.asset_id""",(org_id(),))
 return jsonify([dict(r) for r in rows])

@app.get('/api/search')
def api_search():
 term=(request.args.get('q') or '').strip()
 if len(term)<2:return jsonify([])
 like=f'%{term}%'; out=[]; oid=org_id()
 for r in q("""select a.id,a.asset_id,a.name,a.profession,b.code building,r.code room
  from assets a join buildings b on b.id=a.building_id left join rooms r on r.id=a.room_id
  where b.organization_id=? and (a.asset_id like ? or a.name like ? or a.manufacturer like ?)
  order by a.asset_id limit 8""",(oid,like,like,like)):
  location=' / '.join(x for x in [r['building'],r['room']] if x)
  out.append({'kind':'Asset','title':f"{r['asset_id']} · {r['name']}",'subtitle':f"{r['profession'] or ''} · {location}".strip(' ·'),'url':f"/asset/{r['id']}"})
 for r in q("""select id,code,name,address from buildings
  where organization_id=? and (code like ? or name like ? or address like ?)
  order by name limit 5""",(oid,like,like,like)):
  out.append({'kind':'Budova','title':f"{r['code']} · {r['name']}",'subtitle':r['address'] or '','url':f"/building/{r['id']}"})
 return jsonify(out[:12])

@app.get('/api/health')
def api_health():
 started=time.time(); db_ok=False; db_ms=None; counts={}; oid=org_id()
 try:
  t=time.time(); row=one('select 1 as ok'); db_ms=round((time.time()-t)*1000,1); db_ok=bool(row and row['ok']==1)
  if db_ok and oid:
   counts={
    'buildings':one('select count(*) n from buildings where organization_id=?',(oid,))['n'],
    'assets':one('select count(*) n from assets a join buildings b on b.id=a.building_id where b.organization_id=?',(oid,))['n']
   }
 except Exception:
  db_ok=False
 ok=db_ok
 return jsonify({
  'status':'online' if ok else 'degraded','database':'online' if db_ok else 'offline','api':'online',
  'database_ms':db_ms,'response_ms':round((time.time()-started)*1000,1),'version':'9.0.0.5','counts':counts,
  'database_engine':'PostgreSQL' if USING_POSTGRES else 'SQLite','checked_at':datetime.now().isoformat(timespec='seconds')
 }), (200 if ok else 503)

@app.get('/api/notifications')
def api_notifications():
 out=[]; oid=org_id(); today_iso=date.today().isoformat()
 for r in q("""select i.id,i.title,i.status,i.reported,i.severity,a.id aid,a.asset_id from incidents i
  join assets a on a.id=i.asset_id join buildings b on b.id=a.building_id
  where b.organization_id=? and i.status!='Ukončená' order by i.id desc limit 6""",(oid,)):
  critical=r['severity'] in {'Vysoká','Kritická','Havária'}
  out.append({'key':f"incident:{r['id']}",'title':r['title'],'subtitle':f"{r['asset_id']} · {r['severity']}",'status':r['status'],'level':'red' if critical else 'orange','url':f"/asset/{r['aid']}",'created_at':r['reported'] or ''})
 for r in q("""select w.id,w.title,w.status,w.due,a.id aid,a.asset_id from workorders w
  join assets a on a.id=w.asset_id join buildings b on b.id=a.building_id
  where b.organization_id=? and w.status!='Ukončené' order by w.id desc limit 8""",(oid,)):
  overdue=bool(r['due'] and str(r['due'])[:10]<today_iso)
  out.append({'key':f"workorder:{r['id']}",'title':r['title'],'subtitle':f"{r['asset_id']} · termín {r['due'] or '—'}",'status':'Po termíne' if overdue else r['status'],'level':'red' if overdue else 'blue','url':f"/asset/{r['aid']}",'created_at':r['due'] or ''})
 if session.get('user_role')=='Administrator':
  org=one('select license_until,plan from organizations where id=?',(oid,))
  if org and org['license_until']:
   try:
    days=(datetime.strptime(str(org['license_until'])[:10],'%Y-%m-%d').date()-date.today()).days
    if days<=30:
     out.insert(0,{'key':f'license:{oid}:{org["license_until"]}','title':'Platnosť licencie GAMO','subtitle':('Licencia exspirovala' if days<0 else f'Zostáva {days} dní'),'status':org['plan'],'level':'red' if days<7 else 'orange','url':'/admin','created_at':str(org['license_until'])})
   except Exception:
    pass
 return jsonify(out[:12])

@app.get('/api/setting')
def api_setting():
 if not can('settings_manage'): abort(403)
 section=(request.args.get('section') or '').strip()
 r=one('select v from organization_settings where organization_id=? and k=?',(org_id(),section))
 return jsonify({'value':r['v'] if r else ''})

@app.post('/settings/save')
def save_setting():
 section=(request.form.get('section') or '').strip(); value=(request.form.get('value') or '').strip()
 if not section:
  flash('Chýba názov konfiguračnej sekcie.','error')
 else:
  x('insert into organization_settings(organization_id,k,v) values(?,?,?) on conflict(organization_id,k) do update set v=excluded.v',(org_id(),section,value))
  audit('SETTING_UPDATE',section); flash(f'Konfigurácia „{section}“ bola uložená pre tvoju organizáciu.','success')
 return redirect('/admin')

if __name__=='__main__': app.run(debug=False,port=5050)
