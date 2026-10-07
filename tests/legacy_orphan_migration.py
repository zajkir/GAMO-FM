import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from psycopg.rows import dict_row

from db_migrations import _migration_9

url = os.environ["LEGACY_DATABASE_URL"]

with psycopg.connect(url, row_factory=dict_row) as db:
    db.execute("select set_config('gamo.organization_id','',false)")
    db.execute("select set_config('gamo.platform_admin','1',false)")

    db.execute("""
        create table organizations(
            id bigserial primary key,
            code text unique not null
        )
    """)
    db.execute("""
        create table buildings(
            id bigserial primary key,
            code text,
            name text,
            address text,
            manager text,
            customer text,
            status text,
            organization_id bigint
        )
    """)
    db.execute("""
        create table floors(
            id bigserial primary key,
            building_id bigint,
            code text,
            name text
        )
    """)
    db.execute("""
        create table rooms(
            id bigserial primary key,
            floor_id bigint,
            code text,
            name text,
            area double precision,
            tenant text,
            zone text
        )
    """)
    db.execute("""
        create table assets(
            id bigserial primary key,
            asset_id text,
            name text,
            building_id bigint,
            floor_id bigint,
            room_id bigint,
            profession text,
            grp text,
            type text,
            status text,
            criticality text,
            notes text,
            parent_id bigint,
            organization_id bigint
        )
    """)
    db.execute("""
        create table workorders(
            id bigserial primary key,
            asset_id bigint,
            title text
        )
    """)
    db.execute("""
        create table incidents(
            id bigserial primary key,
            asset_id bigint,
            title text
        )
    """)
    db.execute("""
        create table asset_events(
            id bigserial primary key,
            asset_id bigint,
            organization_id bigint
        )
    """)

    gamo_org = db.execute(
        "insert into organizations(code) values('GAMO') returning id"
    ).fetchone()["id"]

    orphan_id = db.execute(
        "insert into workorders(asset_id,title) values(999999,'Legacy orphan service') returning id"
    ).fetchone()["id"]
    db.commit()

with psycopg.connect(url, row_factory=dict_row) as db:
    db.execute("select set_config('gamo.organization_id','',false)")
    db.execute("select set_config('gamo.platform_admin','1',false)")
    _migration_9(db, True)
    db.commit()

with psycopg.connect(url, row_factory=dict_row) as db:
    db.execute("select set_config('gamo.organization_id','',false)")
    db.execute("select set_config('gamo.platform_admin','1',false)")

    repaired = db.execute(
        """select w.id,w.asset_id,a.asset_id legacy_asset,a.organization_id
           from workorders w join assets a on a.id=w.asset_id
           where w.id=%s""",
        (orphan_id,),
    ).fetchone()
    assert repaired
    assert repaired["legacy_asset"] == "LEGACY-UNASSIGNED"
    assert repaired["organization_id"] == gamo_org

    repair = db.execute(
        """select issue,snapshot
           from data_repair_log
           where source_table='workorders' and source_id=%s""",
        (orphan_id,),
    ).fetchone()
    assert repair
    assert repair["issue"] == "missing_asset"
    assert int(repair["snapshot"]["asset_id"]) == 999999

    fk = db.execute(
        """select 1
           from pg_constraint
           where conname='fk_workorders_asset'"""
    ).fetchone()
    assert fk, "workorders asset foreign key was not created"

    # The original service record survives; only its broken relationship is repaired.
    assert db.execute(
        "select count(*) n from workorders where id=%s",
        (orphan_id,),
    ).fetchone()["n"] == 1

print("Legacy orphan migration test OK")
