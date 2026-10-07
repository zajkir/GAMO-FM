"""Versioned database migrations for GAMO Facility Platform.

Migrations are additive and idempotent. They never drop customer tables or data.
The same migration history works with PostgreSQL (hosted) and SQLite (desktop).
"""
from datetime import datetime


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
                   REFERENCES buildings(id,organization_id) ON DELETE SET NULL;
                 END IF;
               END $$"""
        )
        db.execute(
            """DO $$ BEGIN
                 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_tickets_asset_org') THEN
                   ALTER TABLE tickets ADD CONSTRAINT fk_tickets_asset_org
                   FOREIGN KEY(asset_id,organization_id)
                   REFERENCES assets(id,organization_id) ON DELETE SET NULL;
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
)


def run_migrations(connect, using_postgres):
    """Apply every unapplied migration inside its own transaction."""
    with connect() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations(
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )"""
        )
        db.commit()

    for version, name, migration in MIGRATIONS:
        with connect() as db:
            row = db.execute(
                "select version from schema_migrations where version=%s" if using_postgres
                else "select version from schema_migrations where version=?",
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
