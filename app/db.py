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
        """
    )
    seed_channels(conn)


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
