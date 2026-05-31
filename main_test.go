package main

import (
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

func TestFamilyPlanIncludesPresale(t *testing.T) {
	plan := familyPlan(map[string]int64{})
	if plan["presale"] == nil {
		t.Fatal("family plan must include presale guidance")
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
