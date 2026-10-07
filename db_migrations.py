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
    """Strengthen tenant referential integrity and prevent cross-organization relationships."""
    if not using_postgres:
        return

    # Required organization ownership after legacy rows were backfilled.
    db.execute("ALTER TABLE assets ALTER COLUMN organization_id SET NOT NULL")
    db.execute("ALTER TABLE buildings ALTER COLUMN organization_id SET NOT NULL")
    db.execute("ALTER TABLE users ALTER COLUMN organization_id SET NOT NULL")

    # Composite keys let PostgreSQL verify that an asset can only reference
    # facility records belonging to the same organization.
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

    # These child tables inherit tenant ownership from their parent asset.
    # Explicit foreign keys stop orphan operational records.
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

    # Parent assets must never point into another tenant.
    db.execute(
        """DO $$ BEGIN
             IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_assets_parent_org') THEN
               ALTER TABLE assets ADD CONSTRAINT fk_assets_parent_org
               FOREIGN KEY(parent_id,organization_id)
               REFERENCES assets(id,organization_id) ON DELETE RESTRICT;
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
