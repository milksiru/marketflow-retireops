package main

import (
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

func (a *App) calendarPayload(events []CalendarEvent) map[string]any {
	if len(events) == 0 {
		events = seedCalendarEvents()
	}
	return map[string]any{
		"month":      time.Now().Format("2006-01"),
		"source":     "SEC EDGAR / OpenDART / manual",
		"updated_at": time.Now().Format(time.RFC3339),
		"policy": map[string]any{
			"primary": []string{"SEC EDGAR 공시", "OpenDART 공시"},
			"support": []string{"Nasdaq IPO Calendar", "NYSE IPO Center", "KRX KIND"},
			"labels":  []string{"공식확인", "공시수집", "수동등록", "관찰"},
		},
		"events": events,
	}
}

func (a *App) saveCalendarEvent(payload map[string]any) (CalendarEvent, error) {
	event := CalendarEvent{
		Date:       strings.TrimSpace(stringValue(payload["date"], time.Now().Format("2006-01-02"))),
		Market:     strings.TrimSpace(stringValue(payload["market"], "기타")),
		Company:    strings.TrimSpace(stringValue(payload["company"], "일정")),
		Title:      strings.TrimSpace(stringValue(payload["title"], "")),
		Category:   strings.TrimSpace(stringValue(payload["category"], "시장일정")),
		Status:     strings.TrimSpace(stringValue(payload["status"], "수동등록")),
		Priority:   strings.TrimSpace(stringValue(payload["priority"], "medium")),
		Note:       strings.TrimSpace(stringValue(payload["note"], "")),
		Source:     strings.TrimSpace(stringValue(payload["source"], "manual")),
		SourceURL:  strings.TrimSpace(stringValue(payload["source_url"], "")),
		ExternalID: strings.TrimSpace(stringValue(payload["external_id"], "")),
		Confidence: int(number(payload["confidence"])),
		Official:   boolDefault(payload["official"], false),
		Manual:     true,
	}
	if event.Title == "" {
		event.Title = event.Company + " 일정"
	}
	if event.Confidence == 0 {
		event.Confidence = 70
	}
	if _, err := time.Parse("2006-01-02", event.Date); err != nil {
		return event, fmt.Errorf("invalid date: use YYYY-MM-DD")
	}
	return a.store.UpsertCalendarEvent(event)
}

func (a *App) collectCalendar() (map[string]any, error) {
	events := seedCalendarEvents()
	results := []map[string]any{{"source": "seed", "count": len(events), "status": "ready"}}
	if sec, err := fetchSECCalendarEvents(); err == nil {
		events = append(events, sec...)
		results = append(results, map[string]any{"source": "sec-edgar", "count": len(sec), "status": "ok"})
	} else {
		results = append(results, map[string]any{"source": "sec-edgar", "count": 0, "status": "failed", "error": err.Error()})
	}
	if dart, err := fetchOpenDARTCalendarEvents(); err == nil {
		events = append(events, dart...)
		results = append(results, map[string]any{"source": "opendart", "count": len(dart), "status": "ok"})
	} else if os.Getenv("OPENDART_API_KEY") != "" {
		results = append(results, map[string]any{"source": "opendart", "count": 0, "status": "failed", "error": err.Error()})
	} else {
		results = append(results, map[string]any{"source": "opendart", "count": 0, "status": "skipped", "error": "missing OPENDART_API_KEY"})
	}
	saved := 0
	for _, event := range events {
		if _, err := a.store.UpsertCalendarEvent(event); err == nil {
			saved++
		}
	}
	return map[string]any{"status": "collected", "saved": saved, "sources": results}, nil
}

func seedCalendarEvents() []CalendarEvent {
	return []CalendarEvent{
		{Date: "2026-06-12", Market: "NASDAQ", Company: "SpaceX", Title: "나스닥 스페이스 X 상장 알림", Category: "상장", Status: "관찰", Priority: "high", Note: "사용자 예시 기반 관찰 일정입니다. 실제 상장 확정 여부는 SEC/거래소 공시로 재확인합니다.", Source: "manual-seed", ExternalID: "seed-spacex-2026-06-12", Confidence: 30, Official: false, Manual: false},
		{Date: time.Now().Format("2006-01-02"), Market: "KRX", Company: "오늘 시장 일정", Title: "오늘 공시/실적/배당 캘린더 점검", Category: "시장일정", Status: "대기", Priority: "medium", Note: "자동 수집 소스와 직접 등록 일정을 함께 확인합니다.", Source: "system", ExternalID: "seed-today-market-check", Confidence: 60, Official: false, Manual: false},
	}
}

func fetchSECCalendarEvents() ([]CalendarEvent, error) {
	forms := []string{"S-1", "F-1", "424B4", "EFFECT"}
	out := []CalendarEvent{}
	for _, form := range forms {
		endpoint := "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=" + url.QueryEscape(form) + "&owner=include&count=40&output=atom"
		req, _ := http.NewRequest(http.MethodGet, endpoint, nil)
		req.Header.Set("User-Agent", env("SEC_USER_AGENT", "MarketFlow RetireOps contact@example.com"))
		res, err := (&http.Client{Timeout: 12 * time.Second}).Do(req)
		if err != nil {
			return out, err
		}
		var feed struct {
			Entries []struct {
				Title   string `xml:"title"`
				Updated string `xml:"updated"`
				Link    struct {
					Href string `xml:"href,attr"`
				} `xml:"link"`
				Summary string `xml:"summary"`
			} `xml:"entry"`
		}
		data, readErr := io.ReadAll(res.Body)
		res.Body.Close()
		if readErr != nil {
			return out, readErr
		}
		text := strings.Replace(string(data), `encoding="ISO-8859-1"`, `encoding="UTF-8"`, 1)
		err = xml.NewDecoder(strings.NewReader(text)).Decode(&feed)
		if err != nil {
			return out, err
		}
		for _, entry := range feed.Entries {
			date := strings.SplitN(entry.Updated, "T", 2)[0]
			if date == "" {
				date = time.Now().Format("2006-01-02")
			}
			company := secCompanyName(entry.Title)
			category := "상장"
			status := "공시수집"
			if form == "EFFECT" {
				category, status = "상장", "효력발생"
			}
			out = append(out, CalendarEvent{Date: date, Market: "US", Company: company, Title: form + " 공시 확인: " + company, Category: category, Status: status, Priority: "medium", Note: "SEC EDGAR에서 자동 수집한 IPO/상장 관련 공시입니다.", Source: "SEC EDGAR", SourceURL: entry.Link.Href, ExternalID: "sec:" + form + ":" + entry.Link.Href, Confidence: 90, Official: true})
		}
	}
	return out, nil
}

func secCompanyName(title string) string {
	title = strings.TrimSpace(title)
	if idx := strings.Index(title, " - "); idx > 0 {
		title = strings.TrimSpace(title[idx+3:])
	}
	if idx := strings.Index(title, "("); idx > 0 {
		return strings.TrimSpace(title[:idx])
	}
	return title
}

func fetchOpenDARTCalendarEvents() ([]CalendarEvent, error) {
	key := os.Getenv("OPENDART_API_KEY")
	if key == "" {
		return nil, fmt.Errorf("missing OPENDART_API_KEY")
	}
	end := time.Now()
	start := end.AddDate(0, 0, -14)
	endpoint := "https://opendart.fss.or.kr/api/list.json?crtfc_key=" + url.QueryEscape(key) + "&bgn_de=" + start.Format("20060102") + "&end_de=" + end.Format("20060102") + "&page_count=100"
	req, _ := http.NewRequest(http.MethodGet, endpoint, nil)
	res, err := (&http.Client{Timeout: 12 * time.Second}).Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	var body struct {
		Status  string `json:"status"`
		Message string `json:"message"`
		List    []struct {
			CorpName string `json:"corp_name"`
			Report   string `json:"report_nm"`
			RceptNo  string `json:"rcept_no"`
			RceptDt  string `json:"rcept_dt"`
			Stock    string `json:"stock_code"`
		} `json:"list"`
	}
	if err := json.NewDecoder(res.Body).Decode(&body); err != nil {
		return nil, err
	}
	if body.Status != "000" && body.Status != "013" {
		return nil, fmt.Errorf("opendart %s: %s", body.Status, body.Message)
	}
	out := []CalendarEvent{}
	for _, row := range body.List {
		report := row.Report
		if !strings.Contains(report, "증권신고") && !strings.Contains(report, "투자설명") && !strings.Contains(report, "상장") && !strings.Contains(report, "배당") {
			continue
		}
		category := "시장일정"
		if strings.Contains(report, "증권신고") || strings.Contains(report, "투자설명") || strings.Contains(report, "상장") {
			category = "상장"
		}
		if strings.Contains(report, "배당") {
			category = "배당"
		}
		date := time.Now().Format("2006-01-02")
		if len(row.RceptDt) == 8 {
			date = row.RceptDt[:4] + "-" + row.RceptDt[4:6] + "-" + row.RceptDt[6:]
		}
		out = append(out, CalendarEvent{Date: date, Market: "KRX", Company: row.CorpName, Title: report, Category: category, Status: "공시수집", Priority: "medium", Note: "OpenDART에서 자동 수집한 국내 공시 일정입니다.", Source: "OpenDART", SourceURL: "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + row.RceptNo, ExternalID: "dart:" + row.RceptNo, Confidence: 90, Official: true})
	}
	return out, nil
}
