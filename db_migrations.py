"""Versioned database migrations for GAMO Facility Platform.

Migrations are additive and idempotent. They never drop customer tables or data.
The same migration history works with PostgreSQL (hosted) and SQLite (desktop).
"""
from datetime import datetime, timedelta


def _columns(db, table, using_postgres):
    if using_postgres:
        rows = db.execute(
            "select column_name from information_schema.columns where table_name=%s",
            (table,),
        ).fetchall()
        return {r["column_name"] if isinstance(r, dict) else r[0] for r in rows}
    return {r[1] for r in db.execute(f"pragma table_info({table})").fetchall()}


def _migration_1(db, using_postgres):
    """Tenant-scoped configuration and explicit organization audit ownership."""
    if using_postgres:
        db.execute(
            """CREATE TABLE IF NOT EXISTS organization_settings(
                organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                k TEXT NOT NULL,
                v TEXT,
                PRIMARY KEY(organization_id,k)
            )"""
        )
        if "organization_id" not in _columns(db, "audit_log", True):
            db.execute("ALTER TABLE audit_log ADD COLUMN organization_id BIGINT")
        db.execute(
            """UPDATE audit_log al SET organization_id=u.organization_id
               FROM users u
               WHERE al.organization_id IS NULL AND al.user_id=u.id"""
        )
    else:
        db.execute(
            """CREATE TABLE IF NOT EXISTS organization_settings(
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                k TEXT NOT NULL,
                v TEXT,
                PRIMARY KEY(organization_id,k)
            )"""
        )
        if "organization_id" not in _columns(db, "audit_log", False):
            db.execute("ALTER TABLE audit_log ADD COLUMN organization_id INTEGER")
        db.execute(
            """UPDATE audit_log SET organization_id=(
                SELECT organization_id FROM users WHERE users.id=audit_log.user_id
            ) WHERE organization_id IS NULL"""
        )


def _migration_2(db, using_postgres):
    """Foundation for onboarding and Asset 360 event history."""
    org_cols = _columns(db, "organizations", using_postgres)
    if "onboarding_complete" not in org_cols:
        if using_postgres:
            db.execute("ALTER TABLE organizations ADD COLUMN onboarding_complete BOOLEAN DEFAULT FALSE")
        else:
            db.execute("ALTER TABLE organizations ADD COLUMN onboarding_complete INTEGER DEFAULT 0")
    if using_postgres:
        db.execute(
            """CREATE TABLE IF NOT EXISTS asset_events(
                id BIGSERIAL PRIMARY KEY,
                asset_id BIGINT NOT NULL,
                organization_id BIGINT NOT NULL,
                created TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                user_id BIGINT,
                user_name TEXT,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_asset_events_asset ON asset_events(asset_id,created)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_asset_events_org ON asset_events(organization_id,created)")
    else:
        db.execute(
            """CREATE TABLE IF NOT EXISTS asset_events(
                id INTEGER PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                created TEXT DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                user_name TEXT,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_asset_events_asset ON asset_events(asset_id,created)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_asset_events_org ON asset_events(organization_id,created)")




def _migration_3(db, using_postgres):
    """Make business identifiers tenant-safe instead of globally unique."""
    asset_cols = _columns(db, "assets", using_postgres)
    if "organization_id" not in asset_cols:
        if using_postgres:
            db.execute("ALTER TABLE assets ADD COLUMN organization_id BIGINT")
        else:
            db.execute("ALTER TABLE assets ADD COLUMN organization_id INTEGER")
    if using_postgres:
        db.execute(
            """UPDATE assets a SET organization_id=b.organization_id
               FROM buildings b
               WHERE a.organization_id IS NULL AND a.building_id=b.id"""
        )
        # Legacy tables used global UNIQUE constraints. Commercial tenants need
        # to be able to reuse codes such as A or HVAC-000001 independently.
        db.execute("ALTER TABLE buildings DROP CONSTRAINT IF EXISTS buildings_code_key")
        db.execute("ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_asset_id_key")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_buildings_org_code ON buildings(organization_id,upper(code))")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_assets_org_asset_id ON assets(organization_id,upper(asset_id))")
        db.execute("CREATE INDEX IF NOT EXISTS idx_assets_org ON assets(organization_id)")
    else:
        db.execute(
            """UPDATE assets SET organization_id=(
                SELECT organization_id FROM buildings WHERE buildings.id=assets.building_id
            ) WHERE organization_id IS NULL"""
        )
        # SQLite desktop databases historically had global UNIQUE constraints.
        # Keep them intact for backwards compatibility; the composite indexes
        # document and accelerate the tenant-aware model.
        db.execute("CREATE INDEX IF NOT EXISTS idx_assets_org ON assets(organization_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_buildings_org_code ON buildings(organization_id,code)")




def _migration_4(db, using_postgres):
    """Do not force existing live customers back through first-run onboarding."""
    if using_postgres:
        db.execute(
            """UPDATE organizations o
               SET onboarding_complete=TRUE
               WHERE o.code='GAMO'
                  OR EXISTS (SELECT 1 FROM buildings b WHERE b.organization_id=o.id)"""
        )
    else:
        db.execute(
            """UPDATE organizations
               SET onboarding_complete=1
               WHERE code='GAMO'
                  OR EXISTS (SELECT 1 FROM buildings b WHERE b.organization_id=organizations.id)"""
        )




def _migration_5(db, using_postgres):
    """Customer privacy controls and transparent GAMO support-access history."""
    org_cols = _columns(db, "organizations", using_postgres)
    additions = {
        "support_access_enabled": "BOOLEAN DEFAULT FALSE" if using_postgres else "INTEGER DEFAULT 0",
        "support_access_until": "TIMESTAMPTZ" if using_postgres else "TEXT",
        "privacy_contact": "TEXT",
        "data_region": "TEXT DEFAULT 'Oregon, USA'",
        "retention_days": "INTEGER DEFAULT 3650",
    }
    for column, definition in additions.items():
        if column not in org_cols:
            db.execute(f"ALTER TABLE organizations ADD COLUMN {column} {definition}")
    if using_postgres:
        db.execute(
            """CREATE TABLE IF NOT EXISTS customer_access_log(
                id BIGSERIAL PRIMARY KEY,
                target_organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                actor_user_id BIGINT,
                actor_name TEXT,
                action TEXT NOT NULL,
                reason TEXT,
                created TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                ip TEXT
            )"""
        )
    else:
        db.execute(
            """CREATE TABLE IF NOT EXISTS customer_access_log(
                id INTEGER PRIMARY KEY,
                target_organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                actor_user_id INTEGER,
                actor_name TEXT,
                action TEXT NOT NULL,
                reason TEXT,
                created TEXT DEFAULT CURRENT_TIMESTAMP,
                ip TEXT
            )"""
        )
    db.execute("CREATE INDEX IF NOT EXISTS idx_customer_access_target ON customer_access_log(target_organization_id,created)")


def _migration_6(db, using_postgres):
    """Database-enforced tenant isolation for PostgreSQL via Row Level Security."""
    if not using_postgres:
        return

    direct = {
        "organizations": "id",
        "users": "organization_id",
        "buildings": "organization_id",
        "assets": "organization_id",
        "organization_settings": "organization_id",
        "asset_events": "organization_id",
        "audit_log": "organization_id",
        "customer_access_log": "target_organization_id",
    }
    platform = "current_setting('gamo.platform_admin', true) = '1'"
    tenant = "NULLIF(current_setting('gamo.organization_id', true),'')::bigint"

    for table, column in direct.items():
        policy = f"gamo_tenant_{table}"
        predicate = f"({platform} OR {column} = {tenant})"
        db.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        db.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        db.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        db.execute(f"CREATE POLICY {policy} ON {table} USING ({predicate}) WITH CHECK ({predicate})")

    inherited = {
        "floors": f"({platform} OR EXISTS (SELECT 1 FROM buildings b WHERE b.id=floors.building_id AND b.organization_id={tenant}))",
        "rooms": f"({platform} OR EXISTS (SELECT 1 FROM floors f JOIN buildings b ON b.id=f.building_id WHERE f.id=rooms.floor_id AND b.organization_id={tenant}))",
        "workorders": f"({platform} OR EXISTS (SELECT 1 FROM assets a WHERE a.id=workorders.asset_id AND a.organization_id={tenant}))",
        "incidents": f"({platform} OR EXISTS (SELECT 1 FROM assets a WHERE a.id=incidents.asset_id AND a.organization_id={tenant}))",
        "documents": f"({platform} OR EXISTS (SELECT 1 FROM buildings b WHERE b.id=documents.building_id AND b.organization_id={tenant}))",
    }
    for table, predicate in inherited.items():
        policy = f"gamo_tenant_{table}"
        db.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        db.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        db.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        db.execute(f"CREATE POLICY {policy} ON {table} USING ({predicate}) WITH CHECK ({predicate})")




def _migration_7(db, using_postgres):
    """Temporary passwords must be replaced by the user after first sign-in."""
    user_cols = _columns(db, "users", using_postgres)
    if "must_change_password" not in user_cols:
        if using_postgres:
            db.execute("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE")
        else:
            db.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0")




def _migration_8(db, using_postgres):
    """Optional TOTP MFA with one-time recovery codes."""
    user_cols = _columns(db, "users", using_postgres)
    additions = {
        "mfa_secret": "TEXT",
        "mfa_recovery_codes": "TEXT",
        "mfa_enabled_at": "TIMESTAMPTZ" if using_postgres else "TEXT",
        "mfa_enabled": "BOOLEAN DEFAULT FALSE" if using_postgres else "INTEGER DEFAULT 0",
    }
    for column, definition in additions.items():
        if column not in user_cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")



def _migration_9(db, using_postgres):
    """Repair safe legacy orphans, then enforce tenant referential integrity."""
    if not using_postgres:
        return

    platform = "current_setting('gamo.platform_admin', true) = '1'"

    # Preserve a forensic copy of every automatically repaired legacy record.
    db.execute(
        """CREATE TABLE IF NOT EXISTS data_repair_log(
            id BIGSERIAL PRIMARY KEY,
            source_table TEXT NOT NULL,
            source_id BIGINT,
            issue TEXT NOT NULL,
            snapshot JSONB,
            repaired_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    db.execute("ALTER TABLE data_repair_log ENABLE ROW LEVEL SECURITY")
    db.execute("ALTER TABLE data_repair_log FORCE ROW LEVEL SECURITY")
    db.execute("DROP POLICY IF EXISTS gamo_platform_data_repair_log ON data_repair_log")
    db.execute(
        f"""CREATE POLICY gamo_platform_data_repair_log ON data_repair_log
            USING ({platform}) WITH CHECK ({platform})"""
    )

    gamo = db.execute("select id from organizations where code='GAMO'").fetchone()
    if not gamo:
        raise RuntimeError("Tenant integrity migration requires the internal GAMO organization")
    gamo_org = gamo["id"] if isinstance(gamo, dict) else gamo[0]

    def scalar(row, key="id"):
        if row is None:
            return None
        return row[key] if isinstance(row, dict) else row[0]

    def ensure_legacy_asset():
        row = db.execute(
            "select id from assets where organization_id=%s and asset_id='LEGACY-UNASSIGNED'",
            (gamo_org,),
        ).fetchone()
        if row:
            return scalar(row)

        building = db.execute(
            "select id from buildings where organization_id=%s and code='__LEGACY__'",
            (gamo_org,),
        ).fetchone()
        building_id = scalar(building)
        if not building_id:
            building_id = scalar(
                db.execute(
                    """insert into buildings(code,name,address,manager,customer,status,organization_id)
                       values('__LEGACY__','Legacy / nepriradené záznamy','','GAMO System',
                              'GAMO a.s.','Aktívna',%s) returning id""",
                    (gamo_org,),
                ).fetchone()
            )

        floor = db.execute(
            "select id from floors where building_id=%s and code='LEGACY'",
            (building_id,),
        ).fetchone()
        floor_id = scalar(floor)
        if not floor_id:
            floor_id = scalar(
                db.execute(
                    "insert into floors(building_id,code,name) values(%s,'LEGACY','Nepriradené') returning id",
                    (building_id,),
                ).fetchone()
            )

        room = db.execute(
            "select id from rooms where floor_id=%s and code='LEGACY'",
            (floor_id,),
        ).fetchone()
        room_id = scalar(room)
        if not room_id:
            room_id = scalar(
                db.execute(
                    """insert into rooms(floor_id,code,name,area,tenant,zone)
                       values(%s,'LEGACY','Nepriradené servisné záznamy',0,'GAMO','LEGACY')
                       returning id""",
                    (floor_id,),
                ).fetchone()
            )

        return scalar(
            db.execute(
                """insert into assets(
                       asset_id,name,building_id,floor_id,room_id,profession,grp,type,
                       status,criticality,notes,organization_id
                   ) values(
                       'LEGACY-UNASSIGNED','Legacy / nepriradený asset',%s,%s,%s,
                       'LEGACY','Migrácia','Nepriradené','Mimo prevádzky','C',
                       'Automaticky vytvorené počas bezpečnej migrácie starých orphan záznamov.',%s
                   ) returning id""",
                (building_id, floor_id, room_id, gamo_org),
            ).fetchone()
        )

    # Legacy versions allowed a workorder/incident to be stored with an asset ID
    # that did not exist. We keep the original row and snapshot, but quarantine
    # it under an internal GAMO placeholder so it cannot leak to a customer.
    orphan_workorders = db.execute(
        """select w.id from workorders w
           left join assets a on a.id=w.asset_id
           where w.asset_id is null or a.id is null"""
    ).fetchall()
    orphan_incidents = db.execute(
        """select i.id from incidents i
           left join assets a on a.id=i.asset_id
           where i.asset_id is null or a.id is null"""
    ).fetchall()

    if orphan_workorders or orphan_incidents:
        legacy_asset = ensure_legacy_asset()

        db.execute(
            """insert into data_repair_log(source_table,source_id,issue,snapshot)
               select 'workorders',w.id,'missing_asset',to_jsonb(w)
               from workorders w left join assets a on a.id=w.asset_id
               where w.asset_id is null or a.id is null"""
        )
        db.execute(
            """update workorders w set asset_id=%s
               where w.asset_id is null
                  or not exists(select 1 from assets a where a.id=w.asset_id)""",
            (legacy_asset,),
        )

        db.execute(
            """insert into data_repair_log(source_table,source_id,issue,snapshot)
               select 'incidents',i.id,'missing_asset',to_jsonb(i)
               from incidents i left join assets a on a.id=i.asset_id
               where i.asset_id is null or a.id is null"""
        )
        db.execute(
            """update incidents i set asset_id=%s
               where i.asset_id is null
                  or not exists(select 1 from assets a where a.id=i.asset_id)""",
            (legacy_asset,),
        )

    # Remaining ownership problems are ambiguous and therefore must never be
    # guessed automatically. Abort before adding constraints if one exists.
    checks = (
        ("buildings", "select count(*) n from buildings where organization_id is null"),
        ("users", "select count(*) n from users where organization_id is null"),
        ("assets", """select count(*) n from assets a
                      left join buildings b on b.id=a.building_id
                      where a.organization_id is null or b.id is null
                         or a.organization_id<>b.organization_id"""),
        ("asset parents", """select count(*) n from assets a join assets p on p.id=a.parent_id
                             where a.parent_id is not null and a.organization_id<>p.organization_id"""),
        ("workorders", "select count(*) n from workorders w left join assets a on a.id=w.asset_id where a.id is null"),
        ("incidents", "select count(*) n from incidents i left join assets a on a.id=i.asset_id where a.id is null"),
    )
    for label, sql in checks:
        row = db.execute(sql).fetchone()
        count = row["n"] if isinstance(row, dict) else row[0]
        if count:
            raise RuntimeError(
                f"Tenant integrity migration blocked: {label} contains {count} ambiguous rows"
            )

    db.execute("ALTER TABLE assets ALTER COLUMN organization_id SET NOT NULL")
    db.execute("ALTER TABLE buildings ALTER COLUMN organization_id SET NOT NULL")
    db.execute("ALTER TABLE users ALTER COLUMN organization_id SET NOT NULL")

    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_buildings_id_org ON buildings(id,organization_id)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_assets_id_org ON assets(id,organization_id)")

    db.execute(
        """DO $$ BEGIN
             IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_assets_building_org') THEN
               ALTER TABLE assets ADD CONSTRAINT fk_assets_building_org
               FOREIGN KEY(building_id,organization_id)
               REFERENCES buildings(id,organization_id);
             END IF;
           END $$"""
    )
    db.execute(
        """DO $$ BEGIN
             IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_asset_events_asset_org') THEN
               ALTER TABLE asset_events ADD CONSTRAINT fk_asset_events_asset_org
               FOREIGN KEY(asset_id,organization_id)
               REFERENCES assets(id,organization_id) ON DELETE CASCADE;
             END IF;
           END $$"""
    )
    db.execute(
        """DO $$ BEGIN
             IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_workorders_asset') THEN
               ALTER TABLE workorders ADD CONSTRAINT fk_workorders_asset
               FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE RESTRICT;
             END IF;
           END $$"""
    )
    db.execute(
        """DO $$ BEGIN
             IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_incidents_asset') THEN
               ALTER TABLE incidents ADD CONSTRAINT fk_incidents_asset
               FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE RESTRICT;
             END IF;
           END $$"""
    )
    db.execute(
        """DO $$ BEGIN
             IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_assets_parent_org') THEN
               ALTER TABLE assets ADD CONSTRAINT fk_assets_parent_org
               FOREIGN KEY(parent_id,organization_id)
               REFERENCES assets(id,organization_id) ON DELETE RESTRICT;
             END IF;
           END $$"""
    )



def _migration_10(db, using_postgres):
    """Security policy, authentication telemetry and GDPR request registry."""
    org_cols = _columns(db, "organizations", using_postgres)
    org_additions = {
        "mfa_required": "BOOLEAN DEFAULT FALSE" if using_postgres else "INTEGER DEFAULT 0",
        "retention_last_run": "TIMESTAMPTZ" if using_postgres else "TEXT",
        "backup_last_verified_at": "TIMESTAMPTZ" if using_postgres else "TEXT",
        "backup_last_verified_status": "TEXT",
    }
    for column, definition in org_additions.items():
        if column not in org_cols:
            db.execute(f"ALTER TABLE organizations ADD COLUMN {column} {definition}")

    user_cols = _columns(db, "users", using_postgres)
    if "erased_at" not in user_cols:
        db.execute(
            "ALTER TABLE users ADD COLUMN erased_at TIMESTAMPTZ"
            if using_postgres
            else "ALTER TABLE users ADD COLUMN erased_at TEXT"
        )

    if using_postgres:
        db.execute(
            """CREATE TABLE IF NOT EXISTS auth_events(
                id BIGSERIAL PRIMARY KEY,
                organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
                user_id BIGINT,
                event TEXT NOT NULL,
                success BOOLEAN DEFAULT FALSE,
                detail TEXT,
                ip TEXT,
                user_agent TEXT,
                created TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS privacy_requests(
                id BIGSERIAL PRIMARY KEY,
                organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                subject_user_id BIGINT,
                request_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'COMPLETED',
                requested_by BIGINT,
                note TEXT,
                requested_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMPTZ
            )"""
        )
    else:
        db.execute(
            """CREATE TABLE IF NOT EXISTS auth_events(
                id INTEGER PRIMARY KEY,
                organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                user_id INTEGER,
                event TEXT NOT NULL,
                success INTEGER DEFAULT 0,
                detail TEXT,
                ip TEXT,
                user_agent TEXT,
                created TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS privacy_requests(
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                subject_user_id INTEGER,
                request_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'COMPLETED',
                requested_by INTEGER,
                note TEXT,
                requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )"""
        )

    db.execute("CREATE INDEX IF NOT EXISTS idx_auth_events_org_created ON auth_events(organization_id,created)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_privacy_requests_org_created ON privacy_requests(organization_id,requested_at)")

    if using_postgres:
        platform = "current_setting('gamo.platform_admin', true) = '1'"
        tenant = "NULLIF(current_setting('gamo.organization_id', true),'')::bigint"
        for table in ("auth_events", "privacy_requests"):
            db.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            db.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            db.execute(f"DROP POLICY IF EXISTS gamo_tenant_{table} ON {table}")
            db.execute(
                f"""CREATE POLICY gamo_tenant_{table} ON {table}
                    USING ({platform} OR organization_id={tenant})
                    WITH CHECK ({platform} OR organization_id={tenant})"""
            )


def _migration_11(db, using_postgres):
    """Tenant-isolated customer ticketing and in-app conversation threads."""
    if using_postgres:
        db.execute(
            """CREATE TABLE IF NOT EXISTS tickets(
                id BIGSERIAL PRIMARY KEY,
                organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                ticket_no TEXT NOT NULL,
                created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                assigned_to BIGINT REFERENCES users(id) ON DELETE SET NULL,
                subject TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Požiadavka',
                priority TEXT NOT NULL DEFAULT 'Stredná',
                status TEXT NOT NULL DEFAULT 'Nový',
                building_id BIGINT,
                asset_id BIGINT,
                created TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMPTZ,
                customer_last_read_at TIMESTAMPTZ,
                staff_last_read_at TIMESTAMPTZ,
                customer_last_read_message_id BIGINT DEFAULT 0,
                staff_last_read_message_id BIGINT DEFAULT 0,
                UNIQUE(organization_id,ticket_no)
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS ticket_messages(
                id BIGSERIAL PRIMARY KEY,
                ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                sender_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
                sender_name TEXT,
                body TEXT NOT NULL,
                created TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )"""
        )
    else:
        db.execute(
            """CREATE TABLE IF NOT EXISTS tickets(
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                ticket_no TEXT NOT NULL,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
                subject TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Požiadavka',
                priority TEXT NOT NULL DEFAULT 'Stredná',
                status TEXT NOT NULL DEFAULT 'Nový',
                building_id INTEGER,
                asset_id INTEGER,
                created TEXT DEFAULT CURRENT_TIMESTAMP,
                updated TEXT DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                customer_last_read_at TEXT,
                staff_last_read_at TEXT,
                customer_last_read_message_id INTEGER DEFAULT 0,
                staff_last_read_message_id INTEGER DEFAULT 0,
                UNIQUE(organization_id,ticket_no)
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS ticket_messages(
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                sender_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                sender_name TEXT,
                body TEXT NOT NULL,
                created TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
    db.execute("CREATE INDEX IF NOT EXISTS idx_tickets_org_updated ON tickets(organization_id,updated)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_tickets_org_status ON tickets(organization_id,status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_created ON ticket_messages(ticket_id,created)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ticket_messages_org ON ticket_messages(organization_id,created)")

    if using_postgres:
        platform = "current_setting('gamo.platform_admin', true) = '1'"
        tenant = "NULLIF(current_setting('gamo.organization_id', true),'')::bigint"
        for table in ("tickets","ticket_messages"):
            predicate = f"({platform} OR organization_id={tenant})"
            db.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            db.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            db.execute(f"DROP POLICY IF EXISTS gamo_tenant_{table} ON {table}")
            db.execute(
                f"""CREATE POLICY gamo_tenant_{table} ON {table}
                    USING ({predicate}) WITH CHECK ({predicate})"""
            )

        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_tickets_id_org ON tickets(id,organization_id)")
        db.execute(
            """DO $$ BEGIN
                 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_tickets_building_org') THEN
                   ALTER TABLE tickets ADD CONSTRAINT fk_tickets_building_org
                   FOREIGN KEY(building_id,organization_id)
                   REFERENCES buildings(id,organization_id) ON DELETE RESTRICT;
                 END IF;
               END $$"""
        )
        db.execute(
            """DO $$ BEGIN
                 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_tickets_asset_org') THEN
                   ALTER TABLE tickets ADD CONSTRAINT fk_tickets_asset_org
                   FOREIGN KEY(asset_id,organization_id)
                   REFERENCES assets(id,organization_id) ON DELETE RESTRICT;
                 END IF;
               END $$"""
        )
        db.execute(
            """DO $$ BEGIN
                 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_ticket_messages_ticket_org') THEN
                   ALTER TABLE ticket_messages ADD CONSTRAINT fk_ticket_messages_ticket_org
                   FOREIGN KEY(ticket_id,organization_id)
                   REFERENCES tickets(id,organization_id) ON DELETE CASCADE;
                 END IF;
               END $$"""
        )


def _migration_12(db, using_postgres):
    """Populate the customer's fdsfsdf building with rich, tenant-isolated demo data."""
    ph = "%s" if using_postgres else "?"

    targets = db.execute(
        f"""select b.id building_id,b.organization_id,o.name organization_name
            from buildings b
            join organizations o on o.id=b.organization_id
            where o.code<>'GAMO'
              and (lower(trim(b.name))={ph} or lower(trim(b.code))={ph})
            order by b.id""",
        ("fdsfsdf", "fdsfsdf"),
    ).fetchall()
    if not targets:
        return

    def value(row, key, index=0):
        if row is None:
            return None
        try:
            return row[key]
        except Exception:
            return row[index]

    def insert_id(pg_sql, sqlite_sql, args):
        cur = db.execute(pg_sql if using_postgres else sqlite_sql, args)
        if using_postgres:
            row = cur.fetchone()
            return value(row, "id")
        return cur.lastrowid

    today = datetime.utcnow().date()

    for target in targets:
        building_id = value(target, "building_id")
        organization_id = value(target, "organization_id")
        organization_name = value(target, "organization_name")

        admin = db.execute(
            f"""select id,name from users
                where organization_id={ph} and status='Aktívny'
                order by case when role='Administrator' then 0 when role='Facility Manager' then 1 else 2 end,id
                limit 1""",
            (organization_id,),
        ).fetchone()
        admin_id = value(admin, "id") if admin else None
        admin_name = value(admin, "name") if admin else "Demo používateľ"

        db.execute(
            f"""update buildings
                set address=case when coalesce(trim(address),'')='' then {ph} else address end,
                    manager=case when coalesce(trim(manager),'')='' then {ph} else manager end,
                    customer=case when coalesce(trim(customer),'')='' or customer='GAMO a.s.' then {ph} else customer end,
                    status='Aktívna'
                where id={ph} and organization_id={ph}""",
            ("Testovacia 24, Banská Bystrica", admin_name, organization_name, building_id, organization_id),
        )

        def ensure_floor(code, name):
            row = db.execute(
                f"select id from floors where building_id={ph} and lower(code)=lower({ph}) limit 1",
                (building_id, code),
            ).fetchone()
            if row:
                return value(row, "id")
            return insert_id(
                "insert into floors(building_id,code,name) values(%s,%s,%s) returning id",
                "insert into floors(building_id,code,name) values(?,?,?)",
                (building_id, code, name),
            )

        floor1 = ensure_floor("1.NP", "Prízemie")
        floor2 = ensure_floor("2.NP", "Administratíva")
        floor3 = ensure_floor("3.NP", "Technické podlažie")

        def ensure_room(floor_id, code, name, area, tenant, zone):
            row = db.execute(
                f"select id from rooms where floor_id={ph} and lower(code)=lower({ph}) limit 1",
                (floor_id, code),
            ).fetchone()
            if row:
                return value(row, "id")
            return insert_id(
                "insert into rooms(floor_id,code,name,area,tenant,zone) values(%s,%s,%s,%s,%s,%s) returning id",
                "insert into rooms(floor_id,code,name,area,tenant,zone) values(?,?,?,?,?,?)",
                (floor_id, code, name, area, tenant, zone),
            )

        rooms = {
            "LOBBY": ensure_room(floor1, "LOBBY", "Recepcia a vstupná hala", 74.5, organization_name, "Verejná"),
            "SERVER": ensure_room(floor1, "SERVER-01", "Serverovňa", 31.8, organization_name, "Kritická"),
            "TECH": ensure_room(floor1, "TECH-01", "Technická miestnosť", 42.0, organization_name, "Technická"),
            "OFFICE": ensure_room(floor2, "OFFICE-201", "Open space", 186.4, organization_name, "Administratíva"),
            "MEET": ensure_room(floor2, "MEET-202", "Zasadacia miestnosť", 48.2, organization_name, "Administratíva"),
            "ELE": ensure_room(floor2, "ELE-203", "Elektro rozvodňa", 27.6, organization_name, "Kritická"),
            "HVAC": ensure_room(floor3, "HVAC-301", "Strojovňa VZT", 96.1, organization_name, "Technická"),
            "ARCH": ensure_room(floor3, "ARCH-302", "Archív a sklad", 63.3, organization_name, "Prevádzka"),
        }

        floor_for = {
            "LOBBY": floor1, "SERVER": floor1, "TECH": floor1,
            "OFFICE": floor2, "MEET": floor2, "ELE": floor2,
            "HVAC": floor3, "ARCH": floor3,
        }

        def ensure_asset(asset_id, name, room_key, profession, grp, typ, manufacturer, model, serial,
                         system_id, status, criticality, service, revision, price, ip, protocol, notes):
            row = db.execute(
                f"select id from assets where organization_id={ph} and upper(asset_id)=upper({ph}) limit 1",
                (organization_id, asset_id),
            ).fetchone()
            if row:
                return value(row, "id")
            args = (
                asset_id, name, building_id, floor_for[room_key], rooms[room_key], profession, grp, typ,
                manufacturer, model, serial, system_id, None, status, criticality, service, revision, price,
                (today - timedelta(days=550)).isoformat(), (today + timedelta(days=545)).isoformat(),
                ip, protocol, notes, organization_id,
            )
            return insert_id(
                """insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,serial,system_id,parent_id,status,criticality,service_months,revision_months,purchase_price,installed,warranty,ip,protocol,notes,organization_id)
                   values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                """insert into assets(asset_id,name,building_id,floor_id,room_id,profession,grp,type,manufacturer,model,serial,system_id,parent_id,status,criticality,service_months,revision_months,purchase_price,installed,warranty,ip,protocol,notes,organization_id)
                   values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                args,
            )

        assets = {}
        assets["AHU"] = ensure_asset("HVAC-900001", "VZT jednotka AHU-1", "HVAC", "HVAC", "Vzduchotechnika", "AHU", "Daikin", "D-AHU 8500", "AHU-FDS-001", "SYS-HVAC-01", "Prevádzka", "A", 3, 12, 28400, "10.30.1.20", "BACnet", "Hlavná VZT jednotka pre kancelárske podlažia.")
        assets["FAN"] = ensure_asset("HVAC-900002", "Prívodný ventilátor AHU-1", "HVAC", "HVAC", "Vzduchotechnika", "FAN", "Ziehl-Abegg", "ZA-ECBlue", "FAN-FDS-002", "SYS-HVAC-01", "Prevádzka", "B", 6, 12, 4200, "10.30.1.21", "Modbus", "Podriadený asset VZT jednotky.")
        assets["COOL"] = ensure_asset("HVAC-900003", "Chladiaci modul AHU-1", "HVAC", "HVAC", "Chladenie", "DX", "Daikin", "ERQ250", "DX-FDS-003", "SYS-HVAC-01", "Servis", "B", 6, 12, 8900, "10.30.1.22", "Modbus", "Testovací asset v stave Servis.")
        assets["ELE"] = ensure_asset("ELE-900001", "Hlavný rozvádzač NN", "ELE", "ELE", "Silnoprúd", "LV-SWITCHBOARD", "Schneider Electric", "PrismaSeT", "ELE-FDS-001", "SYS-ELE-01", "Prevádzka", "A", 12, 12, 36500, "10.30.2.10", "Modbus TCP", "Hlavné napájanie objektu.")
        assets["UPS"] = ensure_asset("UPS-900001", "UPS serverovne 20 kVA", "SERVER", "UPS", "Záložné napájanie", "UPS", "Eaton", "93PS 20kVA", "UPS-FDS-001", "SYS-UPS-01", "Servis", "A", 6, 12, 17400, "10.30.2.30", "SNMP", "Kapacita batérií je predmetom servisnej kontroly.")
        assets["CCTV"] = ensure_asset("CCTV-900001", "Kamera hlavného vstupu", "LOBBY", "CCTV", "Kamerový systém", "IP-CAM", "Axis", "P3265-LVE", "CAM-FDS-001", "SYS-CCTV-01", "Prevádzka", "C", 12, 24, 780, "10.30.3.40", "ONVIF", "Vstupná kamera s nočným režimom.")
        assets["ACS"] = ensure_asset("ACS-900001", "Čítačka vstupných kariet", "LOBBY", "ACS", "Prístupový systém", "READER", "HID", "Signo 20", "ACS-FDS-001", "SYS-ACS-01", "Prevádzka", "B", 12, 24, 430, "10.30.3.50", "OSDP", "Hlavný vstup zamestnancov.")
        assets["EPS"] = ensure_asset("EPS-900001", "EPS ústredňa", "TECH", "EPS", "Požiarna signalizácia", "FACP", "Siemens", "FC2020", "EPS-FDS-001", "SYS-EPS-01", "Prevádzka", "A", 6, 12, 12800, "10.30.4.10", "BACnet", "Požiarna ústredňa objektu.")
        assets["ZTI"] = ensure_asset("ZTI-900001", "Obehové čerpadlo vody", "TECH", "ZTI", "Vodné hospodárstvo", "PUMP", "Grundfos", "MAGNA3", "ZTI-FDS-001", "SYS-ZTI-01", "Porucha", "B", 6, 12, 3100, "10.30.5.20", "Modbus", "Nasimulovaná porucha pre test incidentov.")
        assets["MAR"] = ensure_asset("MAR-900001", "BMS regulátor budovy", "SERVER", "MAR", "Meranie a regulácia", "DDC", "Siemens", "PXC4", "MAR-FDS-001", "SYS-BMS-01", "Prevádzka", "A", 6, 12, 9400, "10.30.1.5", "BACnet/IP", "Centrálny regulátor BMS.")
        assets["ENM"] = ensure_asset("ENM-900001", "Hlavný elektromer", "ELE", "ENM", "Energetický monitoring", "METER", "Schneider Electric", "PM8000", "ENM-FDS-001", "SYS-ENM-01", "Prevádzka", "B", 12, 24, 1900, "10.30.2.15", "Modbus TCP", "Fakturačný a prevádzkový energetický monitoring.")
        assets["PO"] = ensure_asset("PO-900001", "Hasiaci prístroj CO2", "SERVER", "PO", "Požiarna ochrana", "EXTINGUISHER", "Gloria", "KS5SE", "PO-FDS-001", "SYS-PO-01", "Prevádzka", "C", 12, 12, 165, "", "", "Kontrolný PO asset pre revízne termíny.")

        db.execute(f"update assets set parent_id={ph} where id in ({ph},{ph}) and organization_id={ph}", (assets["AHU"], assets["FAN"], assets["COOL"], organization_id))

        def ensure_workorder(asset_key, title, kind, priority, status, due_days, supplier, technician, cost, description):
            aid = assets[asset_key]
            row = db.execute(
                f"select id from workorders where asset_id={ph} and title={ph} limit 1",
                (aid, title),
            ).fetchone()
            if row:
                return value(row, "id")
            due = (today + timedelta(days=due_days)).isoformat()
            return insert_id(
                "insert into workorders(asset_id,title,kind,priority,status,due,supplier,technician,cost,description) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                "insert into workorders(asset_id,title,kind,priority,status,due,supplier,technician,cost,description) values(?,?,?,?,?,?,?,?,?,?)",
                (aid, title, kind, priority, status, due, supplier, technician, cost, description),
            )

        ensure_workorder("AHU", "Preventívna údržba VZT", "PM", "Stredná", "Plánované", 14, "KlimaServis SK", "M. Kováč", 420, "Výmena filtrov, kontrola remeňov a meranie prietokov.")
        ensure_workorder("UPS", "Test batériového modulu UPS", "REV", "Vysoká", "Prebieha", 3, "PowerCare s.r.o.", "J. Horváth", 690, "Kapacitný test batérií a kontrola bypassu.")
        ensure_workorder("EPS", "Ročná odborná prehliadka EPS", "REV", "Vysoká", "Plánované", 28, "FireTech SK", "P. Novák", 840, "Kompletná revízia EPS podľa servisného plánu.")
        ensure_workorder("ZTI", "Oprava obehového čerpadla", "OPR", "Kritická", "Prebieha", 1, "AquaServis", "R. Malík", 1250, "Diagnostika ložísk, tesnenia a frekvenčného meniča.")
        ensure_workorder("ELE", "Termovízna kontrola rozvádzača", "REV", "Stredná", "Ukončené", -18, "ElektroCheck", "D. Urban", 510, "Kontrola spojov a teplotných anomálií.")
        ensure_workorder("CCTV", "Čistenie a kontrola kamery", "PM", "Nízka", "Ukončené", -9, "SecureVision", "A. Bielik", 95, "Čistenie optiky a kontrola záznamu.")
        ensure_workorder("PO", "Kontrola hasiaceho prístroja", "REV", "Stredná", "Plánované", -5, "FireTech SK", "P. Novák", 28, "Úmyselne po termíne pre test dashboardu a reportov.")

        def ensure_incident(asset_key, title, severity, status, reported_days, impact, cause, cost):
            aid = assets[asset_key]
            row = db.execute(
                f"select id from incidents where asset_id={ph} and title={ph} limit 1",
                (aid, title),
            ).fetchone()
            if row:
                return value(row, "id")
            reported = (today + timedelta(days=reported_days)).isoformat()
            return insert_id(
                "insert into incidents(asset_id,title,severity,status,reported,impact,cause,cost) values(%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                "insert into incidents(asset_id,title,severity,status,reported,impact,cause,cost) values(?,?,?,?,?,?,?,?)",
                (aid, title, severity, status, reported, impact, cause, cost),
            )

        ensure_incident("ZTI", "Pokles tlaku v cirkulačnom okruhu", "Kritická", "Rieši sa", -1, "Obmedzená dodávka teplej vody na 2. a 3. NP.", "Opotrebované tesnenie čerpadla.", 380)
        ensure_incident("UPS", "Znížená kapacita UPS batérií", "Vysoká", "Pridelená", -3, "Skrátená doba zálohy serverovne.", "Batériový modul pod odporúčanou kapacitou.", 0)
        ensure_incident("CCTV", "Výpadok obrazu kamery pri vstupe", "Stredná", "Vyriešená", -12, "Dočasne bez obrazu hlavného vstupu.", "Poškodený patch kábel.", 74)
        ensure_incident("AHU", "Kolísanie teploty v open space", "Stredná", "Otvorená", -2, "Teplotný komfort na 2. NP.", "Potrebná kontrola regulácie a klapiek.", 0)

        event_specs = [
            ("AHU", "DEMO_SEED", "Testovacia VZT jednotka zaevidovaná", "Asset vytvorený pre komplexný test Asset 360."),
            ("AHU", "SERVICE", "Výmena filtrov", "Simulovaná servisná história: filtre F7 vymenené."),
            ("UPS", "DIAGNOSTIC", "Kapacitný test UPS", "Zistená znížená kapacita batériového modulu."),
            ("ZTI", "FAULT", "Porucha obehového čerpadla", "Incident vytvorený pre test prevádzkového workflow."),
            ("ELE", "REVISION", "Termovízna kontrola", "Bez kritických tepelných anomálií."),
        ]
        for asset_key, event_type, title, detail in event_specs:
            aid = assets[asset_key]
            exists = db.execute(
                f"select id from asset_events where organization_id={ph} and asset_id={ph} and title={ph} limit 1",
                (organization_id, aid, title),
            ).fetchone()
            if not exists:
                db.execute(
                    f"""insert into asset_events(asset_id,organization_id,user_id,user_name,event_type,title,detail)
                        values({ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
                    (aid, organization_id, admin_id, admin_name, event_type, title, detail),
                )

        documents = [
            ("TEST_prevadzkovy_manual.txt", "Technická", "TESTOVACÍ PREVÁDZKOVÝ MANUÁL\nBudova fdsfsdf\n\nObsahuje testovacie technické údaje pre GAMO Facility Platform.\n"),
            ("TEST_plan_revizii.txt", "Revízie", "TESTOVACÍ PLÁN REVÍZIÍ\nEPS: 12 mesiacov\nELE: 12 mesiacov\nUPS: 12 mesiacov\nPO: 12 mesiacov\n"),
            ("TEST_havarijny_postup.txt", "Prevádzka", "TESTOVACÍ HAVARIJNÝ POSTUP\n1. Identifikovať incident.\n2. Informovať facility managera.\n3. Vytvoriť incident/ticket.\n4. Zaznamenať náklady a uzatvorenie.\n"),
        ]
        for name, category, text in documents:
            exists = db.execute(
                f"select id from documents where building_id={ph} and name={ph} limit 1",
                (building_id, name),
            ).fetchone()
            if not exists:
                blob = text.encode("utf-8")
                db.execute(
                    f"insert into documents(building_id,name,category,mime,size,data) values({ph},{ph},{ph},{ph},{ph},{ph})",
                    (building_id, name, category, "text/plain; charset=utf-8", len(blob), blob),
                )

        staff = db.execute(
            f"""select id,name from users
                where organization_id={ph} and status='Aktívny'
                  and role in ('Facility Manager','Administrator','Technik','Servisný technik')
                order by case when role='Facility Manager' then 0 when role='Administrator' then 1 else 2 end,id
                limit 1""",
            (organization_id,),
        ).fetchone()
        staff_id = value(staff, "id") if staff else admin_id
        staff_name = value(staff, "name") if staff else admin_name

        ticket_specs = [
            ("TKT-DEMO-001", "V kanceláriách je príliš teplo", "Budova", "Vysoká", "Rieši sa", assets["AHU"],
             [("Zákazník – test", "Na 2. NP je od rána približne 26 °C. Prosím o kontrolu VZT."),
              (staff_name, "Ticket som prevzal. Skontrolujeme reguláciu AHU-1 a polohu klapiek."),
              ("Zákazník – test", "Ďakujem, problém je najvýraznejší v open space OFFICE-201.")]),
            ("TKT-DEMO-002", "Výmena prístupovej karty", "Prístup", "Stredná", "Čaká na zákazníka", assets["ACS"],
             [("Zákazník – test", "Potrebujeme zablokovať starú kartu a pripraviť novú."),
              (staff_name, "Starú kartu sme zablokovali. Pošlite prosím meno držiteľa novej karty.")]),
            ("TKT-DEMO-003", "UPS hlási servisné upozornenie", "Porucha", "Kritická", "Otvorený", assets["UPS"],
             [("Zákazník – test", "Na UPS svieti servisná výstraha. Serverovňa zatiaľ funguje."),
              (staff_name, "Evidujem. Vytvorený je kapacitný test batériového modulu.")]),
        ]
        for ticket_no, subject, category, priority, status, asset_id, messages in ticket_specs:
            row = db.execute(
                f"select id from tickets where organization_id={ph} and ticket_no={ph} limit 1",
                (organization_id, ticket_no),
            ).fetchone()
            if row:
                ticket_id = value(row, "id")
            else:
                ticket_id = insert_id(
                    """insert into tickets(organization_id,ticket_no,created_by,assigned_to,subject,category,priority,status,building_id,asset_id)
                       values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                    """insert into tickets(organization_id,ticket_no,created_by,assigned_to,subject,category,priority,status,building_id,asset_id)
                       values(?,?,?,?,?,?,?,?,?,?)""",
                    (organization_id, ticket_no, admin_id, staff_id, subject, category, priority, status, building_id, asset_id),
                )
            for sender_name, body in messages:
                exists = db.execute(
                    f"select id from ticket_messages where ticket_id={ph} and organization_id={ph} and body={ph} limit 1",
                    (ticket_id, organization_id, body),
                ).fetchone()
                if not exists:
                    sender_id = staff_id if sender_name == staff_name else admin_id
                    db.execute(
                        f"""insert into ticket_messages(ticket_id,organization_id,sender_user_id,sender_name,body)
                            values({ph},{ph},{ph},{ph},{ph})""",
                        (ticket_id, organization_id, sender_id, sender_name, body),
                    )

        marker = db.execute(
            f"select id from audit_log where organization_id={ph} and action='DEMO_DATA_SEEDED' and detail like {ph} limit 1",
            (organization_id, "%fdsfsdf%"),
        ).fetchone()
        if not marker:
            db.execute(
                f"""insert into audit_log(user_id,user_name,action,detail,ip,organization_id)
                    values({ph},{ph},'DEMO_DATA_SEEDED',{ph},'',{ph})""",
                (admin_id, admin_name, "Budova fdsfsdf naplnená testovacími dátami: priestory, assety, servis, incidenty, dokumenty a tickety.", organization_id),
            )


def _migration_13(db, using_postgres):
    """Platform support inbox read markers for GAMO administrators."""
    cols = _columns(db, "tickets", using_postgres)
    additions = {
        "platform_last_read_at": "TIMESTAMPTZ" if using_postgres else "TEXT",
        "platform_last_read_message_id": "BIGINT DEFAULT 0" if using_postgres else "INTEGER DEFAULT 0",
    }
    for column, definition in additions.items():
        if column not in cols:
            db.execute(f"ALTER TABLE tickets ADD COLUMN {column} {definition}")
    db.execute("CREATE INDEX IF NOT EXISTS idx_tickets_platform_updated ON tickets(updated)")


def _migration_14(db, using_postgres):
    """Asset document center and tenant-safe ticket attachments."""
    if using_postgres:
        db.execute(
            """CREATE TABLE IF NOT EXISTS asset_documents(
                id BIGSERIAL PRIMARY KEY,
                organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                asset_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                category TEXT DEFAULT 'Technická',
                mime TEXT,
                size BIGINT DEFAULT 0,
                uploaded TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                data BYTEA NOT NULL
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS ticket_attachments(
                id BIGSERIAL PRIMARY KEY,
                organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                ticket_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                sender_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
                name TEXT NOT NULL,
                mime TEXT,
                size BIGINT DEFAULT 0,
                uploaded TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                data BYTEA NOT NULL
            )"""
        )
    else:
        db.execute(
            """CREATE TABLE IF NOT EXISTS asset_documents(
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                category TEXT DEFAULT 'Technická',
                mime TEXT,
                size INTEGER DEFAULT 0,
                uploaded TEXT DEFAULT CURRENT_TIMESTAMP,
                data BLOB NOT NULL
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS ticket_attachments(
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                message_id INTEGER NOT NULL REFERENCES ticket_messages(id) ON DELETE CASCADE,
                sender_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                name TEXT NOT NULL,
                mime TEXT,
                size INTEGER DEFAULT 0,
                uploaded TEXT DEFAULT CURRENT_TIMESTAMP,
                data BLOB NOT NULL
            )"""
        )

    db.execute("CREATE INDEX IF NOT EXISTS idx_asset_documents_asset ON asset_documents(organization_id,asset_id,uploaded)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_ticket_attachments_message ON ticket_attachments(organization_id,ticket_id,message_id)")

    if using_postgres:
        platform = "current_setting('gamo.platform_admin', true) = '1'"
        tenant = "NULLIF(current_setting('gamo.organization_id', true),'')::bigint"

        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_ticket_messages_id_org ON ticket_messages(id,organization_id)")

        db.execute(
            """DO $$ BEGIN
                 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_asset_documents_asset_org') THEN
                   ALTER TABLE asset_documents ADD CONSTRAINT fk_asset_documents_asset_org
                   FOREIGN KEY(asset_id,organization_id)
                   REFERENCES assets(id,organization_id) ON DELETE CASCADE;
                 END IF;
               END $$"""
        )
        db.execute(
            """DO $$ BEGIN
                 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_ticket_attachments_ticket_org') THEN
                   ALTER TABLE ticket_attachments ADD CONSTRAINT fk_ticket_attachments_ticket_org
                   FOREIGN KEY(ticket_id,organization_id)
                   REFERENCES tickets(id,organization_id) ON DELETE CASCADE;
                 END IF;
               END $$"""
        )
        db.execute(
            """DO $$ BEGIN
                 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_ticket_attachments_message_org') THEN
                   ALTER TABLE ticket_attachments ADD CONSTRAINT fk_ticket_attachments_message_org
                   FOREIGN KEY(message_id,organization_id)
                   REFERENCES ticket_messages(id,organization_id) ON DELETE CASCADE;
                 END IF;
               END $$"""
        )

        for table in ("asset_documents","ticket_attachments"):
            predicate = f"({platform} OR organization_id={tenant})"
            db.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            db.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            db.execute(f"DROP POLICY IF EXISTS gamo_tenant_{table} ON {table}")
            db.execute(
                f"""CREATE POLICY gamo_tenant_{table} ON {table}
                    USING ({predicate}) WITH CHECK ({predicate})"""
            )


def _migration_15(db, using_postgres):
    """Persistent remembered-device tokens and performance indexes."""
    if using_postgres:
        db.execute(
            """CREATE TABLE IF NOT EXISTS remembered_devices(
                id BIGSERIAL PRIMARY KEY,
                organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT UNIQUE NOT NULL,
                label TEXT,
                user_agent TEXT,
                ip_created TEXT,
                created TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMPTZ NOT NULL,
                revoked_at TIMESTAMPTZ
            )"""
        )
    else:
        db.execute(
            """CREATE TABLE IF NOT EXISTS remembered_devices(
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT UNIQUE NOT NULL,
                label TEXT,
                user_agent TEXT,
                ip_created TEXT,
                created TEXT DEFAULT CURRENT_TIMESTAMP,
                last_used TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            )"""
        )

    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_remembered_devices_user ON remembered_devices(user_id,revoked_at,expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_assets_org_status ON assets(organization_id,status)",
        "CREATE INDEX IF NOT EXISTS idx_assets_org_building ON assets(organization_id,building_id)",
        "CREATE INDEX IF NOT EXISTS idx_buildings_org_name ON buildings(organization_id,name)",
        "CREATE INDEX IF NOT EXISTS idx_users_org_status ON users(organization_id,status)",
        "CREATE INDEX IF NOT EXISTS idx_workorders_asset_status_due ON workorders(asset_id,status,due)",
        "CREATE INDEX IF NOT EXISTS idx_incidents_asset_status ON incidents(asset_id,status)",
        "CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id ON ticket_messages(ticket_id,id)",
        "CREATE INDEX IF NOT EXISTS idx_tickets_org_updated ON tickets(organization_id,updated)",
    )
    for sql in indexes:
        db.execute(sql)

    if using_postgres:
        platform = "current_setting('gamo.platform_admin', true) = '1'"
        tenant = "NULLIF(current_setting('gamo.organization_id', true),'')::bigint"
        db.execute("ALTER TABLE remembered_devices ENABLE ROW LEVEL SECURITY")
        db.execute("ALTER TABLE remembered_devices FORCE ROW LEVEL SECURITY")
        db.execute("DROP POLICY IF EXISTS gamo_tenant_remembered_devices ON remembered_devices")
        db.execute(
            f"""CREATE POLICY gamo_tenant_remembered_devices ON remembered_devices
                USING ({platform} OR organization_id={tenant})
                WITH CHECK ({platform} OR organization_id={tenant})"""
        )


def _migration_16(db, using_postgres):
    """Indexes for large tenant datasets, dashboards, workflow filters and audits."""
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_floors_building_code ON floors(building_id,code)",
        "CREATE INDEX IF NOT EXISTS idx_rooms_floor_code ON rooms(floor_id,code)",
        "CREATE INDEX IF NOT EXISTS idx_assets_org_criticality ON assets(organization_id,criticality)",
        "CREATE INDEX IF NOT EXISTS idx_assets_org_profession ON assets(organization_id,profession)",
        "CREATE INDEX IF NOT EXISTS idx_workorders_status_due_asset ON workorders(status,due,asset_id)",
        "CREATE INDEX IF NOT EXISTS idx_incidents_status_severity_asset ON incidents(status,severity,asset_id)",
        "CREATE INDEX IF NOT EXISTS idx_documents_building_uploaded ON documents(building_id,uploaded)",
        "CREATE INDEX IF NOT EXISTS idx_audit_org_action_created ON audit_log(organization_id,action,created)",
        "CREATE INDEX IF NOT EXISTS idx_tickets_org_creator_updated ON tickets(organization_id,created_by,updated)",
        "CREATE INDEX IF NOT EXISTS idx_ticket_messages_org_ticket_id ON ticket_messages(organization_id,ticket_id,id)",
    )
    for sql in indexes:
        db.execute(sql)

MIGRATIONS = (
    (1, "tenant_settings_and_audit_scope", _migration_1),
    (2, "onboarding_and_asset_events", _migration_2),
    (3, "tenant_safe_business_identifiers", _migration_3),
    (4, "preserve_existing_customer_onboarding_state", _migration_4),
    (5, "customer_privacy_controls", _migration_5),
    (6, "postgres_row_level_security", _migration_6),
    (7, "temporary_password_rotation", _migration_7),
    (8, "totp_mfa_and_recovery_codes", _migration_8),
    (9, "tenant_referential_integrity", _migration_9),
    (10, "customer_security_gdpr_controls", _migration_10),
    (11, "tenant_ticketing_and_messages", _migration_11),
    (12, "seed_fdsfsdf_demo_data", _migration_12),
    (13, "platform_ticket_inbox", _migration_13),
    (14, "asset_documents_and_ticket_attachments", _migration_14),
    (15, "remembered_devices_and_performance_indexes", _migration_15),
    (16, "large_dataset_performance_indexes", _migration_16),
)


def run_migrations(connect, using_postgres):
    """Apply migrations with one startup connection and serialize PostgreSQL deploys."""
    with connect() as db:
        locked = False
        try:
            if using_postgres:
                db.execute("select pg_advisory_lock(64102026)")
                locked = True
            db.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations(
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )"""
            )
            db.commit()

            for version, name, migration in MIGRATIONS:
                placeholder = "%s" if using_postgres else "?"
                row = db.execute(
                    f"select version from schema_migrations where version={placeholder}",
                    (version,),
                ).fetchone()
                if row:
                    continue
                try:
                    migration(db, using_postgres)
                    sql = (
                        "insert into schema_migrations(version,name,applied_at) values(%s,%s,%s)"
                        if using_postgres
                        else "insert into schema_migrations(version,name,applied_at) values(?,?,?)"
                    )
                    db.execute(sql, (version, name, datetime.utcnow().isoformat(timespec="seconds") + "Z"))
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
        finally:
            if using_postgres and locked:
                try:
                    db.execute("select pg_advisory_unlock(64102026)")
                    db.commit()
                except Exception:
                    pass

