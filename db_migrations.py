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


MIGRATIONS = (
    (1, "tenant_settings_and_audit_scope", _migration_1),
    (2, "onboarding_and_asset_events", _migration_2),
    (3, "tenant_safe_business_identifiers", _migration_3),
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
