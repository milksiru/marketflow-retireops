package main

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"
)

var allowedFamily = map[string]bool{
	"cash_stock": true, "park_juyoung_retirement": true, "kim_jihun_retirement": true, "savings": true,
	"car_loan": true, "jeonse_deposit": true, "jeonse_loan": true, "monthly_saving": true,
	"home_target_low": true, "home_target_high": true,
}

var reports = map[string]map[string]any{
	"morning":     {"title": "Morning Brief", "label": "오전 브리핑", "send_time": "07:30", "summary": "미국장 마감과 오늘의 체크포인트를 정리합니다.", "bullets": []string{"미국 기술주 흐름과 반도체 움직임을 확인하세요.", "환율과 미국 10년물 금리를 함께 확인하세요.", "DC 운용은 목표 비중을 기준으로 점검하세요."}},
	"market-open": {"title": "Market Open Watch", "label": "개장 전 체크", "send_time": "08:50", "summary": "환율, 금리, 주요 지수 흐름을 확인합니다.", "bullets": []string{"시장 초반에는 추격보다 확인을 우선하세요.", "반도체 강세와 단기 과열을 함께 점검하세요."}},
	"evening":     {"title": "Evening Brief", "label": "마감 브리핑", "send_time": "18:30", "summary": "한국장 마감과 관심 ETF 변화를 정리합니다.", "bullets": []string{"업종별 확산 여부를 확인하세요.", "다음 거래일 환율과 금리 흐름을 점검하세요."}},
	"weekly":      {"title": "Weekly Report", "label": "주간 리포트", "send_time": "토요일 09:00", "summary": "주간 흐름과 다음 주 관찰 포인트를 제공합니다.", "bullets": []string{"강세와 약세 섹터를 나누어 점검하세요.", "관심 종목은 확신보다 관찰 후보로 관리하세요."}},
	"monthly-dc":  {"title": "Monthly DC Report", "label": "월간 DC 리포트", "send_time": "매월 1일 09:00", "summary": "월간 자산 흐름과 신규 납입금 배분 참고를 정리합니다.", "bullets": []string{"목표 비중과 현재 비중의 차이를 확인하세요.", "이 리포트는 투자 자문이 아닌 참고 신호입니다."}},
}

func listReports() []map[string]any {
	keys := []string{"morning", "market-open", "evening", "weekly", "monthly-dc"}
	out := []map[string]any{}
	for _, key := range keys {
		v := reports[key]
		out = append(out, map[string]any{"report_type": key, "title": v["title"], "label": v["label"], "send_time": v["send_time"], "summary": v["summary"]})
	}
	return out
}
func buildReport(kind string) map[string]any {
	source, ok := reports[kind]
	if !ok {
		source = reports["morning"]
	}
	out := cloneMap(source)
	out["report_type"] = kind
	out["generated_at"] = time.Now().Format(time.RFC3339)
	lines := []string{}
	for _, item := range source["bullets"].([]string) {
		lines = append(lines, "- "+item)
	}
	out["message"] = strings.Join(lines, "\n")
	out["sms_preview"] = "[MarketFlow]\n오늘 시장 흐름을 확인하세요.\nDC 운용은 목표 비중 기준의 참고 정보입니다."
	out["kakao_preview"] = map[string]any{"title": "오늘의 글로벌 시장 브리핑", "summary": source["bullets"], "buttons": []string{"대시보드 열기", "리밸런싱 보기", "위험 알림 보기"}}
	return out
}

func (a *App) snapshot() map[string]any {
	prices, err := a.store.LatestPrices()
	if err != nil || len(prices) == 0 {
		prices = mockPrices()
	}
	prices = dashboardPrices(prices)
	indices := []map[string]any{}
	board := []map[string]any{}
	indexIDs := map[string]bool{"S&P500": true, "Nasdaq": true, "KOSPI": true, "Nikkei": true, "USD/KRW": true, "US10Y": true, "VIX": true, "BTC": true}
	for _, item := range prices {
		tone := "flat"
		if item.ChangePercent >= .25 {
			tone = "up"
		} else if item.ChangePercent <= -.25 {
			tone = "down"
		}
		if (item.AssetID == "USD/KRW" || item.AssetID == "US10Y") && item.ChangePercent > 0 {
			tone = "warn"
		}
		row := map[string]any{"symbol": item.AssetID, "name": item.AssetName, "change": fmt.Sprintf("%+.2f%%", item.ChangePercent), "tone": tone, "spark": sparkFor(item)}
		if indexIDs[item.AssetID] {
			row["value"] = formatPrice(item.Price)
			row["session"] = "Market"
			row["volume"] = "Watch"
			indices = append(indices, row)
		} else if item.AssetID != "WTI" {
			row["price"] = formatPrice(item.Price)
			row["signal"] = signalLabel(item.ChangePercent, item.AssetID)
			board = append(board, row)
		}
	}
	settings, _ := a.store.FamilySettings()
	family := familyPlan(settings)
	rankings := append([]map[string]any{}, board...)
	sort.Slice(rankings, func(i, j int) bool {
		return abs(changeNumber(rankings[i]["change"])) > abs(changeNumber(rankings[j]["change"]))
	})
	if len(rankings) > 8 {
		rankings = rankings[:8]
	}
	for i := range rankings {
		rankings[i]["rank"] = i + 1
	}
	return map[string]any{
		"as_of": time.Now().Format(time.RFC3339), "source": "marketflow-go", "cache_status": "ready", "refresh_seconds": 25,
		"mood":   map[string]any{"state": "Risk On", "score": 74, "plain": "주요 지수와 관심 종목의 최신 조회값을 기준으로 산출한 시장 상태입니다.", "drivers": []string{"관심 종목 흐름 확인", "환율과 금리 점검", "변동성 지수 점검"}},
		"badges": []string{"Risk On", "Live Polling", "Exchange Delay Possible"}, "indices": indices, "trade_board": board,
		"brief":     []string{"기술주 중심 흐름을 확인하세요.", "환율과 금리는 별도의 위험 신호로 함께 확인하세요.", "신규 납입금은 목표 비중을 기준으로 검토하세요."},
		"watchlist": watchlist(board), "sectors": []map[string]any{{"name": "Semiconductor", "change": "+2.10%", "tone": "up"}, {"name": "Mega Tech", "change": "+1.17%", "tone": "up"}, {"name": "Bond", "change": "-0.80%", "tone": "down"}},
		"dc":       map[string]any{"style": "균형 성장형", "risk_score": 62, "rebalance": "목표 비중과 현재 비중 차이를 확인하세요.", "allocation": []map[string]any{{"label": "주식형", "target": 55, "current": 59}, {"label": "채권형", "target": 30, "current": 27}, {"label": "현금성", "target": 15, "current": 14}}, "plain_language": "신규 납입금은 부족한 비중을 채우는 방식으로 검토하세요."},
		"alerts":   []map[string]any{{"level": "watch", "title": "Dollar Strong", "message": "환율 흐름을 확인하세요."}, {"level": "info", "title": "Rebalance Needed", "message": "목표 비중 차이를 점검하세요."}},
		"rankings": rankings, "news_sources": []map[string]any{{"source": "Yahoo Finance", "title": "시장 가격 및 종목 뉴스 확인", "summary": "개별 종목 흐름을 확인합니다.", "url": "https://finance.yahoo.com/"}, {"source": "Reuters Markets", "title": "글로벌 시장 뉴스", "summary": "시장 위험 이벤트를 확인합니다.", "url": "https://www.reuters.com/markets/"}},
		"family_plan": family, "taeri_plan": map[string]any{"name": "태리", "birth": "2022-11-11", "age": "성장 중", "profile": "어린이집 생활", "summary": "생활, 건강, 지원제도를 한곳에서 점검합니다.", "checkpoints": []map[string]any{{"title": "어린이집 생활", "body": "등원, 수면, 식사, 친구 관계에서 달라진 점을 기록합니다."}, {"title": "건강", "body": "예방접종 기록과 다음 검진 일정을 확인합니다."}, {"title": "언어와 정서", "body": "표현 방식과 감정 조절의 변화를 천천히 살펴봅니다."}}, "todo": []string{"어린이집 상담 메모를 정리합니다.", "예방접종과 영유아 검진 일정을 확인합니다.", "지원제도 변경 여부를 주민센터에서 다시 확인합니다."}, "sources": []map[string]any{{"source": "질병관리청 예방접종도우미", "title": "어린이 예방접종 확인", "summary": "예방접종 기록과 지정 의료기관을 확인합니다.", "url": "https://nip.kdca.go.kr/"}, {"source": "아이돌봄서비스", "title": "아이돌봄 지원 확인", "summary": "가정 상황에 맞는 돌봄 서비스 지원 범위를 확인합니다.", "url": "https://www.idolbom.go.kr/front/srvcGuide"}}},
	}
}
func watchlist(board []map[string]any) []map[string]any {
	out := []map[string]any{}
	for _, x := range board {
		symbol := x["symbol"].(string)
		if symbol == "SOXX" || symbol == "QQQ" || symbol == "TLT" || symbol == "SCHD" {
			out = append(out, map[string]any{"symbol": symbol, "name": x["name"], "signal": x["signal"], "risk": "비중 점검", "score": 63, "change": x["change"]})
		}
	}
	return out
}
func familyPlan(v map[string]int64) map[string]any {
	get := func(k string, d int64) int64 {
		if n, ok := v[k]; ok {
			return n
		}
		return d
	}
	cash := get("cash_stock", 80000000)
	wife := get("park_juyoung_retirement", 50000000)
	mine := get("kim_jihun_retirement", 60000000)
	savings := get("savings", 30000000)
	deposit := get("jeonse_deposit", 300000000)
	car := get("car_loan", 30000000)
	loan := get("jeonse_loan", 150000000)
	monthly := get("monthly_saving", 3000000)
	low := get("home_target_low", 600000000)
	high := get("home_target_high", 700000000)
	totalAssets := cash + wife + mine + savings + deposit
	totalDebts := car + loan
	base := cash + wife + mine + savings + deposit - car - loan
	editable := []map[string]any{{"key": "cash_stock", "label": "현금/주식", "value": cash, "category": "asset"}, {"key": "park_juyoung_retirement", "label": "박주영님 퇴직금", "value": wife, "category": "asset"}, {"key": "kim_jihun_retirement", "label": "김지훈님 퇴직금", "value": mine, "category": "asset"}, {"key": "savings", "label": "예적금", "value": savings, "category": "asset"}, {"key": "jeonse_deposit", "label": "전세 보증금", "value": deposit, "category": "asset"}, {"key": "car_loan", "label": "차량 대출", "value": car, "category": "debt"}, {"key": "jeonse_loan", "label": "전세 대출", "value": loan, "category": "debt"}, {"key": "monthly_saving", "label": "월 저축금", "value": monthly, "category": "plan"}, {"key": "home_target_low", "label": "목표 매매가 하단", "value": low, "category": "plan"}, {"key": "home_target_high", "label": "목표 매매가 상단", "value": high, "category": "plan"}}
	return map[string]any{"target": fmt.Sprintf("%s ~ %s", money(low), money(high)), "summary": "가족 자산과 부채를 기준으로 주거 계획을 점검합니다.", "assets": []map[string]any{{"label": "현금/주식", "value": money(cash)}, {"label": "퇴직금", "value": money(wife + mine)}, {"label": "예적금", "value": money(savings)}, {"label": "전세 보증금", "value": money(deposit)}}, "debts": []map[string]any{{"label": "차량 대출", "value": money(car)}, {"label": "전세 대출", "value": money(loan)}}, "metrics": []map[string]any{{"label": "총자산", "value": money(totalAssets)}, {"label": "총부채", "value": money(totalDebts)}, {"label": "가용 자금", "value": money(base)}, {"label": "월 저축금", "value": money(monthly)}, {"label": "목표 하단", "value": money(low)}, {"label": "목표 상단", "value": money(high)}}, "goals": []map[string]any{{"label": "주택 준비금", "current": base, "target": low, "current_text": money(base), "target_text": money(low), "caption": "순자산이 목표 매매가 하단의 몇 %인지 보여줍니다."}, {"label": "비상금", "current": savings, "target": 10000000, "current_text": money(savings), "target_text": money(10000000), "caption": "예적금을 생활 비상금 목표와 비교합니다."}, {"label": "월 저축 습관", "current": monthly, "target": 3000000, "current_text": money(monthly), "target_text": money(3000000), "caption": "월 저축액을 권장 기준과 비교합니다."}}, "steps": []string{"비상금을 먼저 확보합니다.", "부채 상환 조건을 확인합니다.", "주거 목표와 월 저축금을 함께 점검합니다."}, "monthly_saving": money(monthly), "editable": editable, "presale": map[string]any{"title": "왕숙2 A4 본청약", "status": "일정 확인", "notice": "사전청약 당첨 조건과 본청약 일정을 확인하세요.", "expected": "분양가, 계약금, 대출 한도는 공고 시점에 다시 계산합니다.", "plan": "가용 자금과 전세 보증금 반환 시점을 기준으로 계약 가능 범위를 점검합니다.", "focus": []string{"본청약 공고 일정 확인", "계약금과 잔금 현금 흐름 분리", "전세 보증금 반환 시점 점검", "대출 한도와 금리 재확인"}, "note": "최종 조건은 본청약 공고와 금융기관 심사 결과에 따라 달라질 수 있습니다."}}
}
func money(v int64) string {
	manwon := v / 10000
	eok := manwon / 10000
	rest := manwon % 10000
	if eok == 0 {
		return commaInt(manwon) + "만원"
	}
	if rest == 0 {
		return commaInt(eok) + "억원"
	}
	return commaInt(eok) + "억 " + commaInt(rest) + "만원"
}
func commaInt(v int64) string {
	text := strconv.FormatInt(v, 10)
	for i := len(text) - 3; i > 0; i -= 3 {
		text = text[:i] + "," + text[i:]
	}
	return text
}
func formatPrice(v float64) string {
	text := fmt.Sprintf("%.2f", v)
	parts := strings.SplitN(text, ".", 2)
	whole := parts[0]
	for i := len(whole) - 3; i > 0; i -= 3 {
		whole = whole[:i] + "," + whole[i:]
	}
	return whole + "." + parts[1]
}
func signalLabel(v float64, s string) string {
	if s == "TLT" {
		return "Rate Pressure"
	}
	if v >= 2 {
		return "Momentum"
	}
	if v >= .5 {
		return "Trend"
	}
	if v <= -1 {
		return "Volatile"
	}
	return "Neutral"
}
func changeNumber(v any) float64 {
	x, _ := strconv.ParseFloat(strings.TrimSuffix(fmt.Sprint(v), "%"), 64)
	return x
}
func abs(v float64) float64 {
	if v < 0 {
		return -v
	}
	return v
}
