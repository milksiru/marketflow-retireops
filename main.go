package main

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"embed"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/smtp"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	_ "github.com/lib/pq"
)

//go:embed web/index.html
var webFS embed.FS

type App struct {
	store Store
}

type Store interface {
	ListChannels() ([]map[string]any, error)
	UpdateChannel(string, map[string]any) error
	ListSubscriptions() ([]map[string]any, error)
	UpsertSubscription(map[string]any) (int64, error)
	LogNotification(channel, reportType, recipient, title, message, status, detail string) error
	ListLogs() ([]map[string]any, error)
	Stats() (map[string]any, error)
	FamilySettings() (map[string]int64, error)
	UpdateFamilySettings(map[string]any) (map[string]int64, error)
	InsertPrices([]MarketPrice) error
	LatestPrices() ([]MarketPrice, error)
	InsertScore(MarketScore) error
	LatestScore() (*MarketScore, error)
	InsertSignals([]Signal) error
	LatestSignals(int) ([]Signal, error)
	InsertDailyReport(DailyReport) error
	LatestDailyReport() (*DailyReport, error)
	ListCalendarEvents() ([]CalendarEvent, error)
	UpsertCalendarEvent(CalendarEvent) (CalendarEvent, error)
}

type MarketPrice struct {
	AssetID       string  `json:"asset_id"`
	AssetName     string  `json:"asset_name"`
	Price         float64 `json:"price"`
	ChangePercent float64 `json:"change_percent"`
	Volume        float64 `json:"volume"`
	Source        string  `json:"source"`
	ObservedAt    string  `json:"observed_at"`
}

type MarketScore struct {
	ScoreDate  string `json:"score_date"`
	MarketMood string `json:"market_mood"`
	RiskScore  int    `json:"risk_score"`
	RiskLevel  string `json:"risk_level"`
	Summary    string `json:"summary"`
	CreatedAt  string `json:"created_at,omitempty"`
}

type Signal struct {
	AssetID    string `json:"asset_id"`
	SignalType string `json:"signal_type"`
	Score      int    `json:"score"`
	Severity   string `json:"severity"`
	Reason     string `json:"reason"`
	CreatedAt  string `json:"created_at,omitempty"`
}

type DailyReport struct {
	ReportDate string `json:"report_date"`
	Title      string `json:"title"`
	MarketMood string `json:"market_mood"`
	RiskLevel  string `json:"risk_level"`
	Summary    string `json:"summary"`
	DCComment  string `json:"dc_comment"`
	Content    string `json:"content"`
	CreatedAt  string `json:"created_at,omitempty"`
}

type CalendarEvent struct {
	ID         int64  `json:"id,omitempty"`
	Date       string `json:"date"`
	Market     string `json:"market"`
	Company    string `json:"company"`
	Title      string `json:"title"`
	Category   string `json:"category"`
	Status     string `json:"status"`
	Priority   string `json:"priority"`
	Note       string `json:"note"`
	Source     string `json:"source"`
	SourceURL  string `json:"source_url,omitempty"`
	ExternalID string `json:"external_id,omitempty"`
	Confidence int    `json:"confidence"`
	Official   bool   `json:"official"`
	Manual     bool   `json:"manual"`
	CreatedAt  string `json:"created_at,omitempty"`
	UpdatedAt  string `json:"updated_at,omitempty"`
}

func main() {
	store, err := newStore()
	if err != nil {
		log.Fatal(err)
	}
	app := &App{store: store}
	if len(os.Args) > 1 {
		if err := app.runJob(os.Args[1]); err != nil {
			log.Fatal(err)
		}
		return
	}
	addr := env("LISTEN_ADDR", ":8080")
	log.Printf("marketflow-retireops listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, app))
}

func (a *App) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	defer func() {
		if recovered := recover(); recovered != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]any{"error": fmt.Sprint(recovered)})
		}
	}()
	if r.URL.Path == "/" && r.Method == http.MethodGet {
		data, err := webFS.ReadFile("web/index.html")
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write(data)
		return
	}
	if r.URL.Path == "/healthz" && r.Method == http.MethodGet {
		writeJSON(w, http.StatusOK, map[string]any{"ok": true})
		return
	}
	if r.URL.Path == "/api/auth/me" && r.Method == http.MethodGet {
		email, user := authUserFromHeaders(r)
		writeJSON(w, http.StatusOK, map[string]any{
			"authenticated": email != "" || user != "",
			"email":         email,
			"user":          user,
		})
		return
	}
	payload := map[string]any{}
	if r.Body != nil && r.Method != http.MethodGet {
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil && !errors.Is(err, io.EOF) {
			writeJSON(w, http.StatusBadRequest, map[string]any{"error": "invalid JSON"})
			return
		}
	}
	result, status, err := a.route(r.Method, r.URL.Path, payload)
	if err != nil {
		writeJSON(w, status, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, status, result)
}

func (a *App) route(method, path string, payload map[string]any) (any, int, error) {
	switch {
	case method == "GET" && path == "/api/dashboard":
		return a.snapshot(), 200, nil
	case method == "GET" && path == "/api/calendar":
		events, err := a.store.ListCalendarEvents()
		return map[string]any{"calendar": a.calendarPayload(events)}, 200, err
	case method == "GET" && path == "/api/reports":
		return map[string]any{"reports": listReports()}, 200, nil
	case method == "GET" && path == "/api/analyze/latest":
		score, _ := a.store.LatestScore()
		signals, _ := a.store.LatestSignals(25)
		report, _ := a.store.LatestDailyReport()
		return map[string]any{"market_score": score, "signals": signals, "daily_report": report}, 200, nil
	case method == "GET" && path == "/api/market-score/latest":
		score, err := a.store.LatestScore()
		return map[string]any{"market_score": score}, 200, err
	case method == "GET" && path == "/api/signals/latest":
		signals, err := a.store.LatestSignals(50)
		return map[string]any{"signals": signals}, 200, err
	case method == "GET" && path == "/api/reports/daily/latest":
		report, err := a.store.LatestDailyReport()
		return map[string]any{"daily_report": report}, 200, err
	case method == "GET" && strings.HasPrefix(path, "/api/reports/"):
		return buildReport(strings.TrimPrefix(path, "/api/reports/")), 200, nil
	case method == "GET" && (path == "/api/notifications" || path == "/api/notifications/logs"):
		logs, err := a.store.ListLogs()
		return map[string]any{"logs": logs}, 200, err
	case method == "GET" && path == "/api/notifications/stats":
		stats, err := a.store.Stats()
		return stats, 200, err
	case method == "GET" && path == "/api/notifications/channels":
		channels, err := a.store.ListChannels()
		return map[string]any{"channels": channels}, 200, err
	case method == "GET" && path == "/api/subscriptions":
		items, err := a.store.ListSubscriptions()
		return map[string]any{"subscriptions": items}, 200, err
	case method == "GET" && path == "/api/family-plan":
		return map[string]any{"family_plan": a.snapshot()["family_plan"]}, 200, nil
	case method == "POST" && path == "/api/analyze/run":
		collected, err := a.collect(stringValue(payload["provider"], "mock"))
		if err != nil {
			return nil, 500, err
		}
		analyzed, err := a.analyze()
		if err != nil {
			return nil, 500, err
		}
		report, err := a.generateDailyReport()
		return map[string]any{"collector": collected, "analysis": analyzed, "report": report}, 200, err
	case method == "POST" && path == "/api/calendar/collect":
		result, err := a.collectCalendar()
		return result, 200, err
	case method == "POST" && path == "/api/calendar/events":
		event, err := a.saveCalendarEvent(payload)
		return map[string]any{"status": "saved", "event": event}, 200, err
	case method == "POST" && path == "/api/reports/daily/send-sms":
		result, err := a.sendDailyReportSMS()
		return result, 200, err
	case method == "POST" && path == "/api/notifications/sms/test":
		return a.sendSMS("MarketFlow SMS Test", "문자 알림은 투자 참고 정보를 전달합니다. 자동 매수/매도 기능은 제공하지 않습니다.", stringValue(payload["recipient"], ""), "sms-test"), 200, nil
	case method == "POST" && path == "/api/notifications/sms/send":
		return a.sendSMS(stringValue(payload["title"], "MarketFlow"), stringValue(payload["message"], "MarketFlow notification"), stringValue(payload["recipient"], ""), stringValue(payload["report_type"], "manual")), 200, nil
	case method == "POST" && path == "/api/notifications/sms/risk-alert":
		result, err := a.sendRiskAlertSMS()
		return result, 200, err
	case method == "POST" && (path == "/api/notifications/test" || path == "/api/notifications/send"):
		return a.sendNotification(stringValue(payload["channel"], "sms"), stringValue(payload["recipient"], "test-recipient"), stringValue(payload["report_type"], "morning"), stringValue(payload["title"], ""), stringValue(payload["message"], "")), 200, nil
	case method == "POST" && path == "/api/subscriptions":
		id, err := a.store.UpsertSubscription(payload)
		return map[string]any{"status": "saved", "id": id}, 200, err
	case method == "POST" && path == "/api/family-plan":
		updated, err := a.store.UpdateFamilySettings(payload)
		return map[string]any{"status": "saved", "updated": updated, "family_plan": a.snapshot()["family_plan"]}, 200, err
	case method == "PUT" && strings.HasPrefix(path, "/api/notifications/channels/") && strings.HasSuffix(path, "/settings"):
		channel := strings.TrimSuffix(strings.TrimPrefix(path, "/api/notifications/channels/"), "/settings")
		if err := a.store.UpdateChannel(channel, payload); err != nil {
			return nil, 404, err
		}
		return map[string]any{"status": "updated"}, 200, nil
	default:
		return nil, 404, errors.New("not found")
	}
}

func (a *App) runJob(name string) error {
	var result any
	var err error
	switch name {
	case "collect":
		result, err = a.collect(env("MARKETFLOW_COLLECTOR_PROVIDER", "mock"))
	case "calendar":
		result, err = a.collectCalendar()
	case "analyze":
		result, err = a.analyze()
	case "daily-report":
		result, err = a.generateDailyReport()
	case "send-sms-report":
		result, err = a.sendDailyReportSMS()
	case "send-risk-alert":
		result, err = a.sendRiskAlertSMS()
	default:
		result = a.sendNotification(env("REPORT_CHANNEL", "sms"), env("REPORT_RECIPIENT", "scheduled-recipient"), name, "", "")
	}
	if err == nil {
		data, _ := json.Marshal(result)
		fmt.Println(string(data))
	}
	return err
}

func (a *App) collect(provider string) (map[string]any, error) {
	prices := mockPrices()
	if provider == "live" {
		if live, err := fetchLivePrices(); err == nil && len(live) > 0 {
			prices = live
		} else if err != nil {
			return nil, err
		}
	}
	if err := a.store.InsertPrices(prices); err != nil {
		return nil, err
	}
	return map[string]any{"status": "collected", "provider": provider, "count": len(prices)}, nil
}

func (a *App) analyze() (map[string]any, error) {
	prices, err := a.store.LatestPrices()
	if err != nil {
		return nil, err
	}
	if len(prices) == 0 {
		if _, err := a.collect("mock"); err != nil {
			return nil, err
		}
		prices, _ = a.store.LatestPrices()
	}
	lookup := map[string]MarketPrice{}
	for _, item := range prices {
		lookup[item.AssetID] = item
	}
	nasdaq, vix := lookup["Nasdaq"].ChangePercent, lookup["VIX"].Price
	vixChange, yieldChange := lookup["VIX"].ChangePercent, lookup["US10Y"].ChangePercent
	fxChange, soxxChange, oilChange := lookup["USD/KRW"].ChangePercent, lookup["SOXX"].ChangePercent, lookup["WTI"].ChangePercent
	mood := "Neutral"
	if vix >= 25 {
		mood = "Volatility Alert"
	} else if nasdaq > 0 && vixChange < 0 {
		mood = "Risk On"
	} else if nasdaq < 0 && vixChange > 0 {
		mood = "Risk Off"
	}
	if yieldChange >= 1 {
		mood = "Rate Pressure"
	}
	if fxChange >= .8 {
		mood = "Dollar Strong"
	}
	risk := 20
	if vix >= 25 {
		risk += 25
	} else if vix >= 18 {
		risk += 10
	}
	if yieldChange >= 1 {
		risk += 15
	}
	if fxChange >= .8 {
		risk += 15
	}
	if nasdaq <= -1 {
		risk += 15
	}
	if soxxChange <= -1 {
		risk += 10
	}
	if oilChange >= 3 {
		risk += 10
	}
	if risk > 100 {
		risk = 100
	}
	score := MarketScore{time.Now().Format("2006-01-02"), mood, risk, riskLevel(risk), fmt.Sprintf("%s: NASDAQ %+.2f%%, VIX %.2f, USD/KRW %+.2f%%, US10Y %+.2f%%", mood, nasdaq, vix, fxChange, yieldChange), ""}
	signals := buildSignals(prices, risk)
	if err := a.store.InsertScore(score); err != nil {
		return nil, err
	}
	if err := a.store.InsertSignals(signals); err != nil {
		return nil, err
	}
	return map[string]any{"status": "analyzed", "market_score": score, "signals": signals}, nil
}

func buildSignals(prices []MarketPrice, risk int) []Signal {
	result := make([]Signal, 0, len(prices))
	for _, row := range prices {
		score, kind, severity, reason := 50+int(row.ChangePercent*8), "추세 확인", "info", fmt.Sprintf("최근 등락률 %+.2f%% 기준 참고 신호입니다.", row.ChangePercent)
		if row.ChangePercent >= 2 {
			kind, severity, reason = "모멘텀 신호", "positive", "상승 흐름과 거래량을 함께 확인하세요."
		}
		if row.ChangePercent <= -1.5 {
			kind, severity, reason = "위험 신호", "warning", "급락 구간입니다. 비중과 손실 위험을 점검하세요."
		}
		if risk >= 61 && severity == "positive" {
			kind, severity, reason = "공격 신호 보류", "watch", "시장 위험 구간에서는 공격적 접근을 보류합니다."
		}
		if score < 0 {
			score = 0
		}
		if score > 100 {
			score = 100
		}
		result = append(result, Signal{row.AssetID, kind, score, severity, reason, ""})
	}
	return result
}

func (a *App) generateDailyReport() (map[string]any, error) {
	score, err := a.store.LatestScore()
	if err != nil {
		return nil, err
	}
	if score == nil {
		if _, err := a.analyze(); err != nil {
			return nil, err
		}
		score, _ = a.store.LatestScore()
	}
	comment := "신규 납입금은 목표 비중에서 부족한 자산을 보정하는 참고 기준으로 사용하세요."
	if score.RiskScore >= 61 {
		comment = "위험 구간에서는 채권과 현금성 자산의 비중을 우선 점검하세요."
	}
	report := DailyReport{time.Now().Format("2006-01-02"), "MarketFlow Daily Report", score.MarketMood, score.RiskLevel, score.Summary, comment, score.Summary + "\n\nDC 퇴직연금 운용 참고\n" + comment, ""}
	if err := a.store.InsertDailyReport(report); err != nil {
		return nil, err
	}
	return map[string]any{"status": "generated", "report": report}, nil
}

func (a *App) sendDailyReportSMS() (map[string]any, error) {
	report, err := a.store.LatestDailyReport()
	if err != nil {
		return nil, err
	}
	if report == nil {
		if _, err := a.generateDailyReport(); err != nil {
			return nil, err
		}
		report, _ = a.store.LatestDailyReport()
	}
	return a.sendSMS("MarketFlow Daily", fmt.Sprintf("[MarketFlow]\n오늘 시장: %s\n위험도: %s\n\n요약:\n%s\n\nDC 참고:\n%s", report.MarketMood, report.RiskLevel, report.Summary, report.DCComment), "", "daily-report"), nil
}

func (a *App) sendRiskAlertSMS() (map[string]any, error) {
	signals, err := a.store.LatestSignals(10)
	if err != nil {
		return nil, err
	}
	if len(signals) == 0 {
		if _, err := a.analyze(); err != nil {
			return nil, err
		}
		signals, _ = a.store.LatestSignals(10)
	}
	signal := signals[0]
	for _, item := range signals {
		if item.Severity == "warning" {
			signal = item
			break
		}
	}
	message := fmt.Sprintf("[MarketFlow 위험알림]\n%s\n\n상태: %s\n원인: %s\n\n확인:\n%s", signal.SignalType, signal.Severity, signal.Reason, env("DASHBOARD_URL", "http://192.168.55.42:31081"))
	return a.sendSMS("MarketFlow Risk", message, "", "risk-alert"), nil
}

func (a *App) sendNotification(channel, recipient, reportType, title, message string) map[string]any {
	report := buildReport(reportType)
	if title == "" {
		title = report["title"].(string)
	}
	if message == "" {
		message = report["message"].(string)
	}
	var err error
	switch channel {
	case "sms", "kakao":
		log.Printf("[%s] to=%s title=%s message=%s", channel, recipient, title, message)
	case "teams":
		err = postJSON(env("TEAMS_WEBHOOK_URL", recipient), map[string]any{"title": title, "text": message}, nil)
	case "telegram":
		token, chat := os.Getenv("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID", recipient)
		if token == "" || chat == "" {
			err = errors.New("missing Telegram token or chat id")
		} else {
			err = postJSON("https://api.telegram.org/bot"+token+"/sendMessage", map[string]any{"chat_id": chat, "text": title + "\n\n" + message}, nil)
		}
	case "email":
		err = sendEmail(recipient, title, message)
	default:
		err = fmt.Errorf("unknown channel: %s", channel)
	}
	status := "sent"
	detail := ""
	if err != nil {
		status, detail = "failed", err.Error()
	}
	_ = a.store.LogNotification(channel, reportType, recipient, title, message, status, detail)
	result := map[string]any{"status": status}
	if err != nil {
		result["error"] = detail
	}
	return result
}

var phonePattern = regexp.MustCompile(`\D`)

func (a *App) sendSMS(title, message, recipient, reportType string) map[string]any {
	provider := strings.ToLower(env("SMS_PROVIDER", "mock"))
	sender := phonePattern.ReplaceAllString(env("SMS_SENDER_NUMBER", "01000000000"), "")
	if recipient == "" {
		recipient = env("SMS_RECIPIENT_NUMBER", "01000000000")
	}
	recipient = phonePattern.ReplaceAllString(recipient, "")
	var err error
	var result any = map[string]any{"mock": true}
	switch provider {
	case "mock":
		log.Printf("[mock-sms] from=%s to=%s title=%s message=%s", sender, recipient, title, message)
	case "solapi":
		result, err = sendSolapi(sender, recipient, title, message)
	case "sens":
		result, err = sendSens(sender, recipient, title, message)
	default:
		err = fmt.Errorf("unknown SMS provider: %s", provider)
	}
	status, detail := "sent", ""
	if err != nil {
		status, detail = "failed", err.Error()
	}
	_ = a.store.LogNotification("sms", reportType, recipient, title, message, status, detail)
	response := map[string]any{"status": status, "provider": provider, "attempt": 1}
	if err != nil {
		response["error"] = detail
	} else {
		response["result"] = result
	}
	return response
}

func sendSolapi(sender, recipient, title, message string) (any, error) {
	key, secret := os.Getenv("SOLAPI_API_KEY"), os.Getenv("SOLAPI_API_SECRET")
	if key == "" || secret == "" {
		return nil, errors.New("missing Solapi credentials")
	}
	date, salt := time.Now().UTC().Format(time.RFC3339Nano), strconv.FormatInt(time.Now().UnixNano(), 16)
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(date + salt))
	headers := map[string]string{"Authorization": fmt.Sprintf("HMAC-SHA256 apiKey=%s, date=%s, salt=%s, signature=%s", key, date, salt, hex.EncodeToString(mac.Sum(nil)))}
	return postJSONResult("https://api.solapi.com/messages/v4/send", map[string]any{"message": map[string]any{"to": recipient, "from": sender, "text": message, "subject": title}}, headers)
}

func sendSens(sender, recipient, title, message string) (any, error) {
	key, secret, service := os.Getenv("NAVER_SENS_ACCESS_KEY"), os.Getenv("NAVER_SENS_SECRET_KEY"), os.Getenv("NAVER_SENS_SERVICE_ID")
	if key == "" || secret == "" || service == "" {
		return nil, errors.New("missing Naver SENS credentials")
	}
	timestamp, uri := strconv.FormatInt(time.Now().UnixMilli(), 10), "/sms/v2/services/"+service+"/messages"
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte("POST " + uri + "\n" + timestamp + "\n" + key))
	headers := map[string]string{"x-ncp-apigw-timestamp": timestamp, "x-ncp-iam-access-key": key, "x-ncp-apigw-signature-v2": base64.StdEncoding.EncodeToString(mac.Sum(nil))}
	return postJSONResult("https://sens.apigw.ntruss.com"+uri, map[string]any{"type": "LMS", "from": sender, "content": message, "subject": title, "messages": []any{map[string]any{"to": recipient}}}, headers)
}

func postJSON(url string, payload any, headers map[string]string) error {
	_, err := postJSONResult(url, payload, headers)
	return err
}
func postJSONResult(url string, payload any, headers map[string]string) (any, error) {
	if url == "" {
		return nil, errors.New("missing webhook URL")
	}
	data, _ := json.Marshal(payload)
	req, _ := http.NewRequest(http.MethodPost, url, bytes.NewReader(data))
	req.Header.Set("Content-Type", "application/json; charset=utf-8")
	for key, value := range headers {
		req.Header.Set(key, value)
	}
	res, err := (&http.Client{Timeout: 15 * time.Second}).Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	body, _ := io.ReadAll(res.Body)
	if res.StatusCode >= 300 {
		return nil, fmt.Errorf("HTTP %d: %s", res.StatusCode, string(body))
	}
	result := map[string]any{}
	_ = json.Unmarshal(body, &result)
	return result, nil
}

func sendEmail(recipient, title, message string) error {
	host, user, password := os.Getenv("EMAIL_SMTP_HOST"), os.Getenv("EMAIL_SMTP_USER"), os.Getenv("EMAIL_SMTP_PASSWORD")
	if host == "" || user == "" || password == "" {
		return errors.New("missing email config")
	}
	addr := host + ":" + env("EMAIL_SMTP_PORT", "587")
	body := []byte("To: " + recipient + "\r\nSubject: " + title + "\r\n\r\n" + message)
	return smtp.SendMail(addr, smtp.PlainAuth("", user, password, host), user, []string{recipient}, body)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
func authUserFromHeaders(r *http.Request) (string, string) {
	return r.Header.Get("X-Auth-Request-Email"), r.Header.Get("X-Auth-Request-User")
}
func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
func stringValue(value any, fallback string) string {
	if text, ok := value.(string); ok && text != "" {
		return text
	}
	return fallback
}
func riskLevel(score int) string {
	if score <= 20 {
		return "LOW"
	}
	if score <= 40 {
		return "NORMAL"
	}
	if score <= 60 {
		return "WATCH"
	}
	if score <= 80 {
		return "WARNING"
	}
	return "HIGH RISK"
}

type memoryStore struct {
	mu                            sync.Mutex
	channels, subscriptions, logs []map[string]any
	family                        map[string]int64
	prices                        []MarketPrice
	scores                        []MarketScore
	signals                       []Signal
	reports                       []DailyReport
	calendar                      []CalendarEvent
}

func newMemoryStore() *memoryStore {
	m := &memoryStore{family: map[string]int64{}}
	for _, pair := range [][2]string{{"email", "smtp"}, {"teams", "webhook"}, {"telegram", "bot"}, {"sms", "mock"}, {"kakao", "mock"}} {
		m.channels = append(m.channels, map[string]any{"channel_type": pair[0], "provider": pair[1], "enabled": false, "config_json": "{}"})
	}
	return m
}
func (m *memoryStore) ListChannels() ([]map[string]any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return cloneMaps(m.channels), nil
}
func (m *memoryStore) UpdateChannel(channel string, p map[string]any) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, item := range m.channels {
		if item["channel_type"] == channel {
			for k, v := range p {
				item[k] = v
			}
			return nil
		}
	}
	return errors.New("unknown channel")
}
func (m *memoryStore) ListSubscriptions() ([]map[string]any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return cloneMaps(m.subscriptions), nil
}
func (m *memoryStore) UpsertSubscription(p map[string]any) (int64, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	reportType, channel, recipient := stringValue(p["report_type"], "morning"), stringValue(p["channel_type"], "sms"), stringValue(p["recipient"], "scheduled-recipient")
	for _, item := range m.subscriptions {
		if item["report_type"] == reportType && item["channel_type"] == channel && item["recipient"] == recipient {
			for key, value := range p {
				item[key] = value
			}
			return item["id"].(int64), nil
		}
	}
	p = cloneMap(p)
	p["report_type"], p["channel_type"], p["recipient"] = reportType, channel, recipient
	p["id"] = int64(len(m.subscriptions) + 1)
	m.subscriptions = append(m.subscriptions, p)
	return p["id"].(int64), nil
}
func (m *memoryStore) LogNotification(c, r, to, t, msg, s, d string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.logs = append([]map[string]any{{"channel_type": c, "report_type": r, "recipient": to, "title": t, "message": msg, "status": s, "error_message": d, "created_at": time.Now()}}, m.logs...)
	return nil
}
func (m *memoryStore) ListLogs() ([]map[string]any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return cloneMaps(m.logs), nil
}
func (m *memoryStore) Stats() (map[string]any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	sent, failed := 0, 0
	for _, x := range m.logs {
		if x["status"] == "sent" {
			sent++
		} else {
			failed++
		}
	}
	return map[string]any{"total": len(m.logs), "sent": sent, "failed": failed, "active_channels": 0, "active_subscriptions": len(m.subscriptions)}, nil
}
func (m *memoryStore) FamilySettings() (map[string]int64, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := map[string]int64{}
	for k, v := range m.family {
		out[k] = v
	}
	return out, nil
}
func (m *memoryStore) UpdateFamilySettings(p map[string]any) (map[string]int64, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	values := p
	if inner, ok := p["values"].(map[string]any); ok {
		values = inner
	}
	out := map[string]int64{}
	for k, v := range values {
		if allowedFamily[k] {
			n := int64(number(v))
			if n < 0 {
				n = 0
			}
			m.family[k] = n
			out[k] = n
		}
	}
	return out, nil
}
func (m *memoryStore) InsertPrices(v []MarketPrice) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.prices = v
	return nil
}
func (m *memoryStore) LatestPrices() ([]MarketPrice, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]MarketPrice{}, m.prices...), nil
}
func (m *memoryStore) InsertScore(v MarketScore) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.scores = append(m.scores, v)
	return nil
}
func (m *memoryStore) LatestScore() (*MarketScore, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if len(m.scores) == 0 {
		return nil, nil
	}
	v := m.scores[len(m.scores)-1]
	return &v, nil
}
func (m *memoryStore) InsertSignals(v []Signal) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.signals = append(v, m.signals...)
	return nil
}
func (m *memoryStore) LatestSignals(n int) ([]Signal, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if n > len(m.signals) {
		n = len(m.signals)
	}
	return append([]Signal{}, m.signals[:n]...), nil
}
func (m *memoryStore) InsertDailyReport(v DailyReport) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.reports = append(m.reports, v)
	return nil
}
func (m *memoryStore) LatestDailyReport() (*DailyReport, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if len(m.reports) == 0 {
		return nil, nil
	}
	v := m.reports[len(m.reports)-1]
	return &v, nil
}
func (m *memoryStore) ListCalendarEvents() ([]CalendarEvent, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]CalendarEvent{}, m.calendar...), nil
}
func (m *memoryStore) UpsertCalendarEvent(v CalendarEvent) (CalendarEvent, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if v.ExternalID == "" {
		v.ExternalID = fmt.Sprintf("manual:%s:%s:%s", v.Date, v.Market, v.Title)
	}
	now := time.Now().Format(time.RFC3339)
	for i, item := range m.calendar {
		if item.ExternalID != "" && item.ExternalID == v.ExternalID {
			v.ID = item.ID
			v.CreatedAt = item.CreatedAt
			v.UpdatedAt = now
			m.calendar[i] = v
			return v, nil
		}
	}
	v.ID = int64(len(m.calendar) + 1)
	v.CreatedAt = now
	v.UpdatedAt = now
	m.calendar = append(m.calendar, v)
	return v, nil
}
func cloneMap(v map[string]any) map[string]any {
	out := map[string]any{}
	for k, x := range v {
		out[k] = x
	}
	return out
}
func cloneMaps(v []map[string]any) []map[string]any {
	out := make([]map[string]any, len(v))
	for i, x := range v {
		out[i] = cloneMap(x)
	}
	return out
}
func number(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case int:
		return float64(n)
	case int64:
		return float64(n)
	case string:
		x, _ := strconv.ParseFloat(n, 64)
		return x
	}
	return 0
}
