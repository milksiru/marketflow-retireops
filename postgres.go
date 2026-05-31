package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"time"
)

type postgresStore struct{ db *sql.DB }

func newStore() (Store, error) {
	if os.Getenv("DATABASE_HOST") == "" {
		return newMemoryStore(), nil
	}
	port := env("DATABASE_PORT", "5432")
	dsn := fmt.Sprintf("host=%s port=%s dbname=%s user=%s password=%s sslmode=%s",
		os.Getenv("DATABASE_HOST"), port, env("DATABASE_NAME", "marketflow"),
		env("DATABASE_USER", "marketflow"), os.Getenv("DATABASE_PASSWORD"), env("DATABASE_SSLMODE", "disable"))
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, err
	}
	db.SetConnMaxLifetime(5 * time.Minute)
	db.SetMaxOpenConns(8)
	if err := db.Ping(); err != nil {
		return nil, err
	}
	store := &postgresStore{db}
	if err := store.init(); err != nil {
		return nil, err
	}
	return store, nil
}

func (p *postgresStore) init() error {
	_, err := p.db.Exec(`
create table if not exists notification_channels (
 id bigserial primary key, channel_type text not null unique, enabled boolean not null default false,
 provider text not null, sender text, recipient text, config_json jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create table if not exists notification_logs (
 id bigserial primary key, channel_type text not null, report_type text, provider text, recipient text,
 title text, message text, status text not null, error_message text, sent_at timestamptz,
 created_at timestamptz not null default now());
create table if not exists report_subscriptions (
 id bigserial primary key, report_type text not null, channel_type text not null, recipient text not null,
 enabled boolean not null default true, send_time text, timezone text default 'Asia/Seoul',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create table if not exists market_prices (
 id bigserial primary key, asset_id text not null, asset_name text not null, price numeric(18,6),
 change_percent numeric(10,4), volume numeric(24,4), source text not null, observed_at timestamptz not null,
 created_at timestamptz not null default now());
create table if not exists market_scores (
 time timestamptz not null default now(), score_date text, market_mood text not null,
 risk_score numeric(8,4) not null, risk_level text not null, summary text,
 created_at timestamptz not null default now());
create table if not exists asset_signals (
 id bigserial primary key, asset_id text not null, signal_type text not null, score integer not null,
 severity text not null, reason text not null, created_at timestamptz not null default now());
create table if not exists daily_reports (
 id bigserial primary key, report_date text not null, title text not null, market_mood text not null,
 risk_level text not null, summary text not null, dc_comment text not null, content text not null,
 created_at timestamptz not null default now());
create table if not exists family_plan_settings (
 setting_key text primary key, amount bigint not null, updated_at timestamptz not null default now());`)
	if err != nil {
		return err
	}
	for _, item := range [][2]string{{"email", "smtp"}, {"teams", "webhook"}, {"telegram", "bot"}, {"sms", "mock"}, {"kakao", "mock"}} {
		if _, err := p.db.Exec(`insert into notification_channels(channel_type,provider) values($1,$2) on conflict(channel_type) do nothing`, item[0], item[1]); err != nil {
			return err
		}
	}
	return nil
}

func rowsToMaps(rows *sql.Rows) ([]map[string]any, error) {
	defer rows.Close()
	cols, err := rows.Columns()
	if err != nil {
		return nil, err
	}
	out := []map[string]any{}
	for rows.Next() {
		raw := make([]any, len(cols))
		ptr := make([]any, len(cols))
		for i := range raw {
			ptr[i] = &raw[i]
		}
		if err := rows.Scan(ptr...); err != nil {
			return nil, err
		}
		item := map[string]any{}
		for i, k := range cols {
			if b, ok := raw[i].([]byte); ok {
				item[k] = string(b)
			} else {
				item[k] = raw[i]
			}
		}
		out = append(out, item)
	}
	return out, rows.Err()
}
func (p *postgresStore) ListChannels() ([]map[string]any, error) {
	r, e := p.db.Query(`select * from notification_channels order by channel_type`)
	if e != nil {
		return nil, e
	}
	return rowsToMaps(r)
}
func (p *postgresStore) UpdateChannel(c string, v map[string]any) error {
	config, _ := json.Marshal(v["config"])
	res, e := p.db.Exec(`update notification_channels set enabled=coalesce($1,enabled),provider=coalesce(nullif($2,''),provider),config_json=$3,updated_at=now() where channel_type=$4`, boolValue(v["enabled"]), stringValue(v["provider"], ""), string(config), c)
	if e != nil {
		return e
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return fmt.Errorf("unknown channel: %s", c)
	}
	return nil
}
func (p *postgresStore) ListSubscriptions() ([]map[string]any, error) {
	r, e := p.db.Query(`select * from report_subscriptions order by report_type,channel_type,recipient`)
	if e != nil {
		return nil, e
	}
	return rowsToMaps(r)
}
func (p *postgresStore) UpsertSubscription(v map[string]any) (int64, error) {
	var id int64
	reportType, channel, recipient := stringValue(v["report_type"], "morning"), stringValue(v["channel_type"], "sms"), stringValue(v["recipient"], "scheduled-recipient")
	e := p.db.QueryRow(`
with existing as (
 update report_subscriptions set enabled=$4,send_time=$5,timezone=$6,updated_at=now()
 where report_type=$1 and channel_type=$2 and recipient=$3 returning id
), inserted as (
 insert into report_subscriptions(report_type,channel_type,recipient,enabled,send_time,timezone)
 select $1,$2,$3,$4,$5,$6 where not exists(select 1 from existing) returning id
)
select id from existing union all select id from inserted limit 1`,
		reportType, channel, recipient, boolDefault(v["enabled"], true), stringValue(v["send_time"], "07:30"), stringValue(v["timezone"], "Asia/Seoul")).Scan(&id)
	return id, e
}
func (p *postgresStore) LogNotification(c, r, to, t, msg, s, d string) error {
	_, e := p.db.Exec(`insert into notification_logs(channel_type,report_type,recipient,title,message,status,error_message,sent_at) values($1,$2,$3,$4,$5,$6,nullif($7,''),case when $6='sent' then now() end)`, c, r, to, t, msg, s, d)
	return e
}
func (p *postgresStore) ListLogs() ([]map[string]any, error) {
	r, e := p.db.Query(`select * from notification_logs order by id desc limit 100`)
	if e != nil {
		return nil, e
	}
	return rowsToMaps(r)
}
func (p *postgresStore) Stats() (map[string]any, error) {
	out := map[string]any{}
	for k, q := range map[string]string{"total": `select count(*) from notification_logs`, "sent": `select count(*) from notification_logs where status='sent'`, "failed": `select count(*) from notification_logs where status='failed'`, "active_channels": `select count(*) from notification_channels where enabled=true`, "active_subscriptions": `select count(*) from report_subscriptions where enabled=true`} {
		var n int
		if e := p.db.QueryRow(q).Scan(&n); e != nil {
			return nil, e
		}
		out[k] = n
	}
	return out, nil
}
func (p *postgresStore) FamilySettings() (map[string]int64, error) {
	r, e := p.db.Query(`select setting_key,amount from family_plan_settings`)
	if e != nil {
		return nil, e
	}
	defer r.Close()
	out := map[string]int64{}
	for r.Next() {
		var k string
		var v int64
		if e := r.Scan(&k, &v); e != nil {
			return nil, e
		}
		out[k] = v
	}
	return out, r.Err()
}
func (p *postgresStore) UpdateFamilySettings(v map[string]any) (map[string]int64, error) {
	values := v
	if x, ok := v["values"].(map[string]any); ok {
		values = x
	}
	out := map[string]int64{}
	for k, x := range values {
		if !allowedFamily[k] {
			continue
		}
		n := int64(number(x))
		if n < 0 {
			n = 0
		}
		if _, e := p.db.Exec(`insert into family_plan_settings(setting_key,amount) values($1,$2) on conflict(setting_key) do update set amount=excluded.amount,updated_at=now()`, k, n); e != nil {
			return nil, e
		}
		out[k] = n
	}
	return out, nil
}
func (p *postgresStore) InsertPrices(v []MarketPrice) error {
	tx, e := p.db.Begin()
	if e != nil {
		return e
	}
	defer tx.Rollback()
	for _, x := range v {
		if _, e = tx.Exec(`insert into market_prices(asset_id,asset_name,price,change_percent,volume,source,observed_at) values($1,$2,$3,$4,$5,$6,$7)`, x.AssetID, x.AssetName, x.Price, x.ChangePercent, x.Volume, x.Source, x.ObservedAt); e != nil {
			return e
		}
	}
	return tx.Commit()
}
func (p *postgresStore) LatestPrices() ([]MarketPrice, error) {
	r, e := p.db.Query(`select distinct on(asset_id) asset_id,asset_name,price,change_percent,volume,source,observed_at::text from market_prices order by asset_id,id desc`)
	if e != nil {
		return nil, e
	}
	defer r.Close()
	out := []MarketPrice{}
	for r.Next() {
		var x MarketPrice
		if e := r.Scan(&x.AssetID, &x.AssetName, &x.Price, &x.ChangePercent, &x.Volume, &x.Source, &x.ObservedAt); e != nil {
			return nil, e
		}
		out = append(out, x)
	}
	return out, r.Err()
}
func (p *postgresStore) InsertScore(v MarketScore) error {
	_, e := p.db.Exec(`insert into market_scores(time,score_date,market_mood,risk_score,risk_level,summary) values(now(),$1,$2,$3,$4,$5)`, v.ScoreDate, v.MarketMood, v.RiskScore, v.RiskLevel, v.Summary)
	return e
}
func (p *postgresStore) LatestScore() (*MarketScore, error) {
	x := MarketScore{}
	e := p.db.QueryRow(`select score_date,market_mood,risk_score,risk_level,summary,created_at::text from market_scores order by time desc limit 1`).Scan(&x.ScoreDate, &x.MarketMood, &x.RiskScore, &x.RiskLevel, &x.Summary, &x.CreatedAt)
	if e == sql.ErrNoRows {
		return nil, nil
	}
	return &x, e
}
func (p *postgresStore) InsertSignals(v []Signal) error {
	tx, e := p.db.Begin()
	if e != nil {
		return e
	}
	defer tx.Rollback()
	for _, x := range v {
		if _, e = tx.Exec(`insert into asset_signals(asset_id,signal_type,score,severity,reason) values($1,$2,$3,$4,$5)`, x.AssetID, x.SignalType, x.Score, x.Severity, x.Reason); e != nil {
			return e
		}
	}
	return tx.Commit()
}
func (p *postgresStore) LatestSignals(n int) ([]Signal, error) {
	r, e := p.db.Query(`select asset_id,signal_type,score,severity,reason,created_at::text from asset_signals order by id desc limit $1`, n)
	if e != nil {
		return nil, e
	}
	defer r.Close()
	out := []Signal{}
	for r.Next() {
		var x Signal
		if e := r.Scan(&x.AssetID, &x.SignalType, &x.Score, &x.Severity, &x.Reason, &x.CreatedAt); e != nil {
			return nil, e
		}
		out = append(out, x)
	}
	return out, r.Err()
}
func (p *postgresStore) InsertDailyReport(v DailyReport) error {
	_, e := p.db.Exec(`insert into daily_reports(report_date,title,market_mood,risk_level,summary,dc_comment,content) values($1,$2,$3,$4,$5,$6,$7)`, v.ReportDate, v.Title, v.MarketMood, v.RiskLevel, v.Summary, v.DCComment, v.Content)
	return e
}
func (p *postgresStore) LatestDailyReport() (*DailyReport, error) {
	x := DailyReport{}
	e := p.db.QueryRow(`select report_date,title,market_mood,risk_level,summary,dc_comment,content,created_at::text from daily_reports order by id desc limit 1`).Scan(&x.ReportDate, &x.Title, &x.MarketMood, &x.RiskLevel, &x.Summary, &x.DCComment, &x.Content, &x.CreatedAt)
	if e == sql.ErrNoRows {
		return nil, nil
	}
	return &x, e
}
func boolValue(v any) *bool {
	if b, ok := v.(bool); ok {
		return &b
	}
	return nil
}
func boolDefault(v any, d bool) bool {
	if b, ok := v.(bool); ok {
		return b
	}
	return d
}
