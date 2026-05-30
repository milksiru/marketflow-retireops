import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


DB_PATH = os.environ.get("MARKETFLOW_DB", "/data/marketflow.db")


@contextmanager
def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        init(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init(conn):
    conn.executescript(
        """
        create table if not exists notification_channels (
          id integer primary key autoincrement,
          channel_type text not null unique,
          enabled integer not null default 0,
          provider text not null,
          config_json text not null default '{}',
          created_at text not null,
          updated_at text not null
        );

        create table if not exists notification_logs (
          id integer primary key autoincrement,
          channel_type text not null,
          report_type text not null,
          recipient text not null,
          title text not null,
          message text not null,
          status text not null,
          error_message text,
          sent_at text,
          created_at text not null
        );

        create table if not exists report_subscriptions (
          id integer primary key autoincrement,
          report_type text not null,
          channel_type text not null,
          recipient text not null,
          enabled integer not null default 1,
          send_time text not null,
          timezone text not null default 'Asia/Seoul',
          created_at text not null,
          updated_at text not null
        );

        create table if not exists market_prices (
          id integer primary key autoincrement,
          asset_id text not null,
          asset_name text not null,
          price real,
          change_percent real,
          volume real,
          source text not null,
          observed_at text not null,
          created_at text not null
        );

        create table if not exists analysis_runs (
          id integer primary key autoincrement,
          run_type text not null,
          status text not null,
          started_at text not null,
          finished_at text,
          error_message text
        );

        create table if not exists market_scores (
          id integer primary key autoincrement,
          score_date text not null,
          market_mood text not null,
          risk_score integer not null,
          risk_level text not null,
          summary text not null,
          created_at text not null
        );

        create table if not exists asset_signals (
          id integer primary key autoincrement,
          asset_id text not null,
          signal_type text not null,
          score integer not null,
          severity text not null,
          reason text not null,
          created_at text not null
        );

        create table if not exists daily_reports (
          id integer primary key autoincrement,
          report_date text not null,
          title text not null,
          market_mood text not null,
          risk_level text not null,
          summary text not null,
          dc_comment text not null,
          content text not null,
          created_at text not null
        );
        """
    )
    ensure_columns(conn, "notification_channels", {"sender": "text", "recipient": "text"})
    ensure_columns(conn, "notification_logs", {"provider": "text"})
    seed_channels(conn)


def ensure_columns(conn, table, columns):
    existing = {row["name"] for row in conn.execute(f"pragma table_info({table})")}
    for name, column_type in columns.items():
        if name not in existing:
            conn.execute(f"alter table {table} add column {name} {column_type}")


def seed_channels(conn):
    channels = [
        ("email", "smtp", False),
        ("teams", "webhook", False),
        ("telegram", "bot", False),
        ("sms", "mock", False),
        ("kakao", "mock", False),
    ]
    for channel_type, provider, enabled in channels:
        conn.execute(
            """
            insert or ignore into notification_channels
              (channel_type, enabled, provider, config_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (channel_type, int(enabled), provider, "{}", now_iso(), now_iso()),
        )


def list_channels():
    with connect() as conn:
        return [dict(row) for row in conn.execute("select * from notification_channels order by channel_type")]


def update_channel(channel, payload):
    with connect() as conn:
        existing = conn.execute(
            "select * from notification_channels where channel_type = ?", (channel,)
        ).fetchone()
        if not existing:
            raise KeyError(channel)
        config = payload.get("config", {})
        conn.execute(
            """
            update notification_channels
            set enabled = ?, provider = ?, config_json = ?, updated_at = ?
            where channel_type = ?
            """,
            (
                int(bool(payload.get("enabled", existing["enabled"]))),
                payload.get("provider", existing["provider"]),
                json.dumps(config, ensure_ascii=False),
                now_iso(),
                channel,
            ),
        )


def list_subscriptions():
    with connect() as conn:
        rows = conn.execute(
            "select * from report_subscriptions order by report_type, channel_type, recipient"
        ).fetchall()
        return [dict(row) for row in rows]


def upsert_subscription(payload):
    report_type = payload.get("report_type", "morning")
    channel_type = payload.get("channel_type", "sms")
    recipient = payload.get("recipient", "scheduled-recipient")
    enabled = int(bool(payload.get("enabled", True)))
    send_time = payload.get("send_time", "07:30")
    timezone_name = payload.get("timezone", "Asia/Seoul")
    with connect() as conn:
        existing = conn.execute(
            """
            select id from report_subscriptions
            where report_type = ? and channel_type = ? and recipient = ?
            """,
            (report_type, channel_type, recipient),
        ).fetchone()
        if existing:
            conn.execute(
                """
                update report_subscriptions
                set enabled = ?, send_time = ?, timezone = ?, updated_at = ?
                where id = ?
                """,
                (enabled, send_time, timezone_name, now_iso(), existing["id"]),
            )
            return existing["id"]
        cursor = conn.execute(
            """
            insert into report_subscriptions
              (report_type, channel_type, recipient, enabled, send_time, timezone, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (report_type, channel_type, recipient, enabled, send_time, timezone_name, now_iso(), now_iso()),
        )
        return cursor.lastrowid


def log_notification(channel, report_type, recipient, title, message, status, error_message=None):
    with connect() as conn:
        conn.execute(
            """
            insert into notification_logs
              (channel_type, report_type, recipient, title, message, status, error_message, sent_at, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel,
                report_type,
                recipient,
                title,
                message,
                status,
                error_message,
                now_iso() if status == "sent" else None,
                now_iso(),
            ),
        )


def create_analysis_run(run_type):
    with connect() as conn:
        cursor = conn.execute(
            "insert into analysis_runs (run_type, status, started_at) values (?, ?, ?)",
            (run_type, "running", now_iso()),
        )
        return cursor.lastrowid


def finish_analysis_run(run_id, status="succeeded", error_message=None):
    with connect() as conn:
        conn.execute(
            "update analysis_runs set status = ?, finished_at = ?, error_message = ? where id = ?",
            (status, now_iso(), error_message, run_id),
        )


def insert_market_prices(rows):
    with connect() as conn:
        conn.executemany(
            """
            insert into market_prices
              (asset_id, asset_name, price, change_percent, volume, source, observed_at, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["asset_id"],
                    row.get("asset_name", row["asset_id"]),
                    row.get("price"),
                    row.get("change_percent"),
                    row.get("volume"),
                    row.get("source", "mock"),
                    row.get("observed_at", now_iso()),
                    now_iso(),
                )
                for row in rows
            ],
        )
        return len(rows)


def latest_market_prices():
    with connect() as conn:
        rows = conn.execute(
            """
            select mp.* from market_prices mp
            join (
              select asset_id, max(id) as max_id from market_prices group by asset_id
            ) latest on latest.max_id = mp.id
            order by asset_id
            """
        ).fetchall()
        return [dict(row) for row in rows]


def insert_market_score(score):
    with connect() as conn:
        conn.execute(
            """
            insert into market_scores
              (score_date, market_mood, risk_score, risk_level, summary, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (
                score["score_date"],
                score["market_mood"],
                score["risk_score"],
                score["risk_level"],
                score["summary"],
                now_iso(),
            ),
        )


def latest_market_score():
    with connect() as conn:
        row = conn.execute("select * from market_scores order by id desc limit 1").fetchone()
        return dict(row) if row else None


def insert_asset_signals(signals):
    with connect() as conn:
        conn.executemany(
            """
            insert into asset_signals
              (asset_id, signal_type, score, severity, reason, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["asset_id"],
                    row["signal_type"],
                    row["score"],
                    row["severity"],
                    row["reason"],
                    now_iso(),
                )
                for row in signals
            ],
        )
        return len(signals)


def latest_asset_signals(limit=50):
    with connect() as conn:
        rows = conn.execute(
            "select * from asset_signals order by id desc limit ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def insert_daily_report(report):
    with connect() as conn:
        conn.execute(
            """
            insert into daily_reports
              (report_date, title, market_mood, risk_level, summary, dc_comment, content, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["report_date"],
                report["title"],
                report["market_mood"],
                report["risk_level"],
                report["summary"],
                report["dc_comment"],
                report["content"],
                now_iso(),
            ),
        )


def latest_daily_report():
    with connect() as conn:
        row = conn.execute("select * from daily_reports order by id desc limit 1").fetchone()
        return dict(row) if row else None


def list_logs(limit=100):
    with connect() as conn:
        rows = conn.execute(
            "select * from notification_logs order by id desc limit ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def notification_stats():
    with connect() as conn:
        total = conn.execute("select count(*) as value from notification_logs").fetchone()["value"]
        sent = conn.execute("select count(*) as value from notification_logs where status = 'sent'").fetchone()["value"]
        failed = conn.execute("select count(*) as value from notification_logs where status = 'failed'").fetchone()["value"]
        active_channels = conn.execute(
            "select count(*) as value from notification_channels where enabled = 1"
        ).fetchone()["value"]
        subscriptions = conn.execute(
            "select count(*) as value from report_subscriptions where enabled = 1"
        ).fetchone()["value"]
        return {
            "total": total,
            "sent": sent,
            "failed": failed,
            "active_channels": active_channels,
            "active_subscriptions": subscriptions,
        }


if os.environ.get("DATABASE_HOST"):
    from app import db_pg as _pg

    connect = _pg.connect
    init = _pg.init
    list_channels = _pg.list_channels
    update_channel = _pg.update_channel
    list_subscriptions = _pg.list_subscriptions
    upsert_subscription = _pg.upsert_subscription
    log_notification = _pg.log_notification
    list_logs = _pg.list_logs
    create_analysis_run = _pg.create_analysis_run
    finish_analysis_run = _pg.finish_analysis_run
    insert_market_prices = _pg.insert_market_prices
    latest_market_prices = _pg.latest_market_prices
    insert_market_score = _pg.insert_market_score
    latest_market_score = _pg.latest_market_score
    insert_asset_signals = _pg.insert_asset_signals
    latest_asset_signals = _pg.latest_asset_signals
    insert_daily_report = _pg.insert_daily_report
    latest_daily_report = _pg.latest_daily_report
    notification_stats = _pg.notification_stats
