import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

import pg8000.dbapi


def enabled():
    return bool(os.environ.get("DATABASE_HOST"))


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _conn():
    return pg8000.dbapi.connect(
        host=os.environ.get("DATABASE_HOST", "marketflow-db"),
        port=int(os.environ.get("DATABASE_PORT", "5432")),
        database=os.environ.get("DATABASE_NAME", "marketflow"),
        user=os.environ.get("DATABASE_USER", "marketflow"),
        password=os.environ.get("DATABASE_PASSWORD", ""),
        timeout=10,
    )


def _rows(cursor):
    cols = [col[0] for col in cursor.description or []]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


@contextmanager
def connect():
    conn = _conn()
    try:
        init(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


@contextmanager
def cursor(conn):
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def init(conn):
    with cursor(conn) as cur:
        cur.execute("create extension if not exists timescaledb")
        cur.execute(
            """
            create table if not exists notification_channels (
              id bigserial primary key,
              channel_type text not null unique,
              enabled boolean not null default false,
              provider text not null,
              sender text,
              recipient text,
              config_json jsonb not null default '{}'::jsonb,
              created_at timestamptz not null default now(),
              updated_at timestamptz not null default now()
            )
            """
        )
        cur.execute(
            """
            create table if not exists notification_logs (
              id bigserial primary key,
              channel_type text not null,
              report_type text,
              provider text,
              recipient text,
              title text,
              message text,
              status text not null,
              error_message text,
              sent_at timestamptz,
              created_at timestamptz not null default now()
            )
            """
        )
        cur.execute(
            """
            create table if not exists report_subscriptions (
              id bigserial primary key,
              report_type text not null,
              channel_type text not null,
              recipient text not null,
              enabled boolean not null default true,
              send_time text,
              timezone text default 'Asia/Seoul',
              created_at timestamptz not null default now(),
              updated_at timestamptz not null default now()
            )
            """
        )
        cur.execute(
            """
            create table if not exists market_prices (
              id bigserial primary key,
              asset_id text not null,
              asset_name text not null,
              price numeric(18,6),
              change_percent numeric(10,4),
              volume numeric(24,4),
              source text not null,
              observed_at timestamptz not null,
              created_at timestamptz not null default now()
            )
            """
        )
        cur.execute(
            """
            create table if not exists analysis_runs (
              id bigserial primary key,
              run_type text not null,
              status text not null,
              started_at timestamptz not null default now(),
              finished_at timestamptz,
              error_message text
            )
            """
        )
        cur.execute(
            """
            create table if not exists market_scores (
              time timestamptz not null default now(),
              score_date text,
              market_mood text not null,
              risk_score numeric(8,4) not null,
              risk_level text not null,
              summary text,
              created_at timestamptz not null default now()
            )
            """
        )
        cur.execute(
            """
            create table if not exists asset_signals (
              id bigserial primary key,
              asset_id text not null,
              signal_type text not null,
              score integer not null,
              severity text not null,
              reason text not null,
              created_at timestamptz not null default now()
            )
            """
        )
        cur.execute(
            """
            create table if not exists daily_reports (
              id bigserial primary key,
              report_date text not null,
              title text not null,
              market_mood text not null,
              risk_level text not null,
              summary text not null,
              dc_comment text not null,
              content text not null,
              created_at timestamptz not null default now()
            )
            """
        )
        cur.execute(
            """
            create table if not exists market_ticks (
              time timestamptz not null,
              symbol text not null,
              name text,
              market text,
              price numeric(18,6),
              change_rate numeric(10,4),
              volume numeric(24,4),
              source text,
              primary key(time, symbol)
            )
            """
        )
        cur.execute("select create_hypertable('market_ticks', 'time', if_not_exists => true)")
        cur.execute("select create_hypertable('market_scores', 'time', if_not_exists => true)")
    seed_channels(conn)


def seed_channels(conn):
    channels = [("email", "smtp", False), ("teams", "webhook", False), ("telegram", "bot", False), ("sms", "mock", False), ("kakao", "mock", False)]
    with cursor(conn) as cur:
        for channel_type, provider, is_enabled in channels:
            cur.execute(
                """
                insert into notification_channels
                  (channel_type, enabled, provider, config_json, created_at, updated_at)
                values (%s, %s, %s, %s::jsonb, now(), now())
                on conflict (channel_type) do nothing
                """,
                (channel_type, is_enabled, provider, "{}"),
            )


def list_channels():
    with connect() as conn, cursor(conn) as cur:
        cur.execute("select * from notification_channels order by channel_type")
        return _rows(cur)


def update_channel(channel, payload):
    with connect() as conn, cursor(conn) as cur:
        cur.execute("select * from notification_channels where channel_type = %s", (channel,))
        existing = _rows(cur)
        if not existing:
            raise KeyError(channel)
        current = existing[0]
        cur.execute(
            """
            update notification_channels
            set enabled = %s, provider = %s, config_json = %s::jsonb, updated_at = now()
            where channel_type = %s
            """,
            (bool(payload.get("enabled", current["enabled"])), payload.get("provider", current["provider"]), json.dumps(payload.get("config", {}), ensure_ascii=False), channel),
        )


def list_subscriptions():
    with connect() as conn, cursor(conn) as cur:
        cur.execute("select * from report_subscriptions order by report_type, channel_type, recipient")
        return _rows(cur)


def upsert_subscription(payload):
    with connect() as conn, cursor(conn) as cur:
        cur.execute(
            """
            insert into report_subscriptions
              (report_type, channel_type, recipient, enabled, send_time, timezone, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, now(), now())
            on conflict do nothing
            returning id
            """,
            (
                payload.get("report_type", "morning"),
                payload.get("channel_type", "sms"),
                payload.get("recipient", "scheduled-recipient"),
                bool(payload.get("enabled", True)),
                payload.get("send_time", "07:30"),
                payload.get("timezone", "Asia/Seoul"),
            ),
        )
        row = cur.fetchone()
        return row[0] if row else None


def log_notification(channel, report_type, recipient, title, message, status, error_message=None):
    with connect() as conn, cursor(conn) as cur:
        cur.execute(
            """
            insert into notification_logs
              (channel_type, report_type, recipient, title, message, status, error_message, sent_at, created_at)
            values (%s, %s, %s, %s, %s, %s, %s, case when %s = 'sent' then now() else null end, now())
            """,
            (channel, report_type, recipient, title, message, status, error_message, status),
        )


def list_logs(limit=100):
    with connect() as conn, cursor(conn) as cur:
        cur.execute("select * from notification_logs order by id desc limit %s", (limit,))
        return _rows(cur)


def create_analysis_run(run_type):
    with connect() as conn, cursor(conn) as cur:
        cur.execute("insert into analysis_runs (run_type, status, started_at) values (%s, %s, now()) returning id", (run_type, "running"))
        return cur.fetchone()[0]


def finish_analysis_run(run_id, status="succeeded", error_message=None):
    with connect() as conn, cursor(conn) as cur:
        cur.execute("update analysis_runs set status = %s, finished_at = now(), error_message = %s where id = %s", (status, error_message, run_id))


def insert_market_prices(rows):
    with connect() as conn, cursor(conn) as cur:
        for row in rows:
            cur.execute(
                """
                insert into market_prices
                  (asset_id, asset_name, price, change_percent, volume, source, observed_at, created_at)
                values (%s, %s, %s, %s, %s, %s, %s, now())
                """,
                (row["asset_id"], row.get("asset_name", row["asset_id"]), row.get("price"), row.get("change_percent"), row.get("volume"), row.get("source", "mock"), row.get("observed_at", now_iso())),
            )
            cur.execute(
                """
                insert into market_ticks (time, symbol, name, price, change_rate, volume, source)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (time, symbol) do update set price = excluded.price, change_rate = excluded.change_rate, volume = excluded.volume, source = excluded.source
                """,
                (row.get("observed_at", now_iso()), row["asset_id"], row.get("asset_name", row["asset_id"]), row.get("price"), row.get("change_percent"), row.get("volume"), row.get("source", "mock")),
            )
        return len(rows)


def latest_market_prices():
    with connect() as conn, cursor(conn) as cur:
        cur.execute(
            """
            select distinct on (asset_id) * from market_prices
            order by asset_id, id desc
            """
        )
        return _rows(cur)


def insert_market_score(score):
    with connect() as conn, cursor(conn) as cur:
        cur.execute(
            """
            insert into market_scores (time, score_date, market_mood, risk_score, risk_level, summary, created_at)
            values (now(), %s, %s, %s, %s, %s, now())
            """,
            (score["score_date"], score["market_mood"], score["risk_score"], score["risk_level"], score["summary"]),
        )


def latest_market_score():
    with connect() as conn, cursor(conn) as cur:
        cur.execute("select * from market_scores order by time desc limit 1")
        rows = _rows(cur)
        return rows[0] if rows else None


def insert_asset_signals(signals):
    with connect() as conn, cursor(conn) as cur:
        for row in signals:
            cur.execute(
                "insert into asset_signals (asset_id, signal_type, score, severity, reason, created_at) values (%s, %s, %s, %s, %s, now())",
                (row["asset_id"], row["signal_type"], row["score"], row["severity"], row["reason"]),
            )
        return len(signals)


def latest_asset_signals(limit=50):
    with connect() as conn, cursor(conn) as cur:
        cur.execute("select * from asset_signals order by id desc limit %s", (limit,))
        return _rows(cur)


def insert_daily_report(report):
    with connect() as conn, cursor(conn) as cur:
        cur.execute(
            """
            insert into daily_reports
              (report_date, title, market_mood, risk_level, summary, dc_comment, content, created_at)
            values (%s, %s, %s, %s, %s, %s, %s, now())
            """,
            (report["report_date"], report["title"], report["market_mood"], report["risk_level"], report["summary"], report["dc_comment"], report["content"]),
        )


def latest_daily_report():
    with connect() as conn, cursor(conn) as cur:
        cur.execute("select * from daily_reports order by id desc limit 1")
        rows = _rows(cur)
        return rows[0] if rows else None


def notification_stats():
    with connect() as conn, cursor(conn) as cur:
        cur.execute(
            """
            select
              (select count(*) from notification_logs) as total,
              (select count(*) from notification_logs where status = 'sent') as sent,
              (select count(*) from notification_logs where status = 'failed') as failed,
              (select count(*) from notification_channels where enabled = true) as active_channels,
              (select count(*) from report_subscriptions where enabled = true) as active_subscriptions
            """
        )
        return _rows(cur)[0]

