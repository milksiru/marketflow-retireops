package main

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHealthAndAnalyze(t *testing.T) {
	app := &App{store: newMemoryStore()}

	health := httptest.NewRecorder()
	app.ServeHTTP(health, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if health.Code != http.StatusOK || !strings.Contains(health.Body.String(), `"ok":true`) {
		t.Fatalf("unexpected health response: %d %s", health.Code, health.Body.String())
	}

	analyze := httptest.NewRecorder()
	app.ServeHTTP(analyze, httptest.NewRequest(http.MethodPost, "/api/analyze/run", strings.NewReader(`{"provider":"mock"}`)))
	if analyze.Code != http.StatusOK || !strings.Contains(analyze.Body.String(), `"status":"analyzed"`) {
		t.Fatalf("unexpected analyze response: %d %s", analyze.Code, analyze.Body.String())
	}
}

func TestFormatPrice(t *testing.T) {
	if got := formatPrice(1128.4); got != "1,128.40" {
		t.Fatalf("formatPrice returned %q", got)
	}
}

func TestMoneyUsesReadableKoreanUnits(t *testing.T) {
	tests := map[int64]string{
		91330000:  "9,133만원",
		600000000: "6억원",
		613300000: "6억 1,330만원",
	}
	for value, want := range tests {
		if got := money(value); got != want {
			t.Fatalf("money(%d) returned %q, want %q", value, got, want)
		}
	}
}

func TestSparkForUsesDistinctFallbackAndCachedCloses(t *testing.T) {
	samsung := MarketPrice{AssetID: "005930", Price: 73500, ChangePercent: 1.1}
	hynix := MarketPrice{AssetID: "000660", Price: 208500, ChangePercent: 2.8}
	if fmt.Sprint(sparkFor(samsung)) == fmt.Sprint(sparkFor(hynix)) {
		t.Fatal("fallback sparklines must differ by asset")
	}
	first, second := 101.0, 103.0
	storeSpark("005930", []*float64{&first, nil, &second})
	if got := sparkFor(samsung); len(got) != 2 || got[0] != first || got[1] != second {
		t.Fatalf("sparkFor must use cached market closes, got %#v", got)
	}
}

func TestFamilyPlanIncludesPresale(t *testing.T) {
	plan := familyPlan(map[string]int64{})
	if plan["presale"] == nil {
		t.Fatal("family plan must include presale guidance")
	}
	if metrics := plan["metrics"].([]map[string]any); len(metrics) != 6 {
		t.Fatalf("family plan must expose six summary metrics, got %d", len(metrics))
	}
	goals := plan["goals"].([]map[string]any)
	if goals[0]["label"] != "주택 준비금" || goals[0]["current_text"] == "" || goals[0]["target_text"] == "" {
		t.Fatalf("family goals must explain current and target values: %#v", goals[0])
	}
}

func TestMemorySubscriptionUpsert(t *testing.T) {
	store := newMemoryStore()
	first, _ := store.UpsertSubscription(map[string]any{"recipient": "01012345678", "send_time": "07:30"})
	second, _ := store.UpsertSubscription(map[string]any{"recipient": "01012345678", "send_time": "08:00"})
	items, _ := store.ListSubscriptions()
	if first != second || len(items) != 1 || items[0]["send_time"] != "08:00" {
		t.Fatalf("subscription was not updated: %#v", items)
	}
}
