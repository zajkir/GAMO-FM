# GAMO a.s. Facility Platform

GAMO a.s. Facility Platform je multi-tenant facility-management aplikácia pre správu budov, priestorov, technológií, údržby, incidentov, dokumentácie, reportingu a zákazníckej podpory.

## Architektúra

- **Web backend:** Python 3.12 + Flask
- **Databáza:** PostgreSQL v produkcii, SQLite pre lokálne/regresné testy
- **Frontend:** HTML/Jinja, CSS, vanilla JavaScript
- **Desktop klient:** Windows aplikácia otvára cloudovú GAMO platformu v izolovanom Microsoft Edge application režime; embedded WebView je iba fallback
- **Windows installer:** Inno Setup
- **Produkčný server:** Gunicorn
- **CI/CD:** GitHub Actions + Render Auto-Deploy
- **Excel exporty:** openpyxl
- **MFA:** TOTP cez pyotp + QR provisioning

Zákazník nepotrebuje Python, PostgreSQL, Render ani vývojové nástroje. Dostane Windows installer, nainštaluje GAMO a.s., prihlási sa a pracuje s cloudovými dátami svojej organizácie.

## Hlavné funkcie

- zákaznícke organizácie, licencie a Customer 360
- budovy → podlažia → miestnosti → assety
- Asset ID, Asset Tag, System ID a Parent/Child väzby
- preventívna údržba, revízie, opravy a automatický maintenance planner
- incidenty, poruchy a havárie
- dokumenty budov a assetov
- tickety a live in-app komunikácia zákazník ↔ správca ↔ GAMO support
- notifikácie, globálne vyhľadávanie a dashboard
- manažérske Reporty & BI + XLSX export
- interaktívny 3D Digital Twin budovy
- onboarding nového zákazníka
- Privacy & Security Center
- GDPR export/anonymizácia používateľských údajov
- zákaznícky ZIP Backup V3 s SHA-256 integritou
- automatický Windows updater s kontrolou SHA-256

## Bezpečnosť a súkromie

Produkčné PostgreSQL nasadenie používa viac vrstiev ochrany:

- tenant filtre v aplikačných query
- PostgreSQL Row Level Security
- databázové foreign keys proti cross-tenant väzbám
- CSRF ochranu zápisových operácií
- role-based oprávnenia
- TOTP MFA a jednorazové recovery kódy
- časovo obmedzený GAMO support consent
- audit loginov, support prístupov a prevádzkových operácií
- bezpečné upload limity a kontrolu typov súborov
- secure cookies, HSTS a bezpečnostné HTTP hlavičky

Detailné zákaznícke dáta GAMO administrátor neotvára mimo explicitne povoleného support režimu. Ticketová komunikácia je samostatný komunikačný kanál.

## Produkčné premenné

Pre produkciu nastav minimálne:

- DATABASE_URL
- GAMO_ADMIN_PASSWORD pri inicializácii úplne novej databázy
- GAMO_SECRET_KEY je odporúčané explicitne nastaviť; ak chýba, aplikácia vytvorí stabilný náhodný secret v databáze
- GAMO_HTTPS=1 je pri PostgreSQL/cloud režime predvolená hodnota

Python runtime je v repozitári pripnutý cez .python-version, aby sa Render správal rovnako ako CI.

## Health check

Minimálny serverový health endpoint:

GET /healthz

Nevracia zákaznícke dáta a je vhodný pre platformový health check. Prihlásená aplikácia má navyše /api/health s tenant-scoped prevádzkovými informáciami.

## Testovanie

GitHub workflow .github/workflows/quality.yml kontroluje:

- Python syntax
- JavaScript syntax
- Windows installer/updater regressie
- SQLite end-to-end scenáre
- PostgreSQL scenáre cez non-superuser rolu s RLS
- customer isolation / IDOR testy
- MFA, Privacy Center, GDPR a backup integritu
- ticket live messaging
- asset editáciu a hierarchy validáciu
- legacy databázové migrácie
- preventívnu údržbu a application polish

Zmena sa nemá označiť za hotovú, kým príslušný workflow nie je zelený.

## Windows release

Workflow .github/workflows/build-windows.yml vytvára:

- GAMO_FM.exe
- GAMO_FM_<version>.exe portable build
- GAMO_FM_Setup_<version>.exe

Pri pushi release zmien do main vytvorí GitHub Release, vypočíta SHA-256 a aktualizuje update.json.

Pre reálne firemné nasadenie je odporúčané nakonfigurovať Authenticode/code-signing certifikát v GitHub Secrets. Bez dôveryhodného podpisu môže podniková Windows Application Control politika blokovať executable aj vtedy, keď je samotná aplikácia v poriadku.

## Dáta a aktualizácie

Cloudové zákaznícke dáta nie sú uložené v inštalačnom adresári Windows aplikácie. Upgrade alebo uninstall preto zákaznícku PostgreSQL databázu nemaže. Updater zachováva aj prípadnú historickú lokálnu SQLite databázu starších desktop verzií.

Databázové zmeny sa robia verzovanými, transakčnými migráciami v db_migrations.py. Historické migrácie sa spätne nemažú ani neprepisujú.
