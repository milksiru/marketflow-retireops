package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"sync"
	"time"
)

var (
	sparkMu       sync.RWMutex
	sparkCache    = map[string][]float64{}
	liveMu        sync.Mutex
	livePrices    []MarketPrice
	liveFetchedAt time.Time
)

var symbols = []struct{ yahoo, id, name string }{
	{"^GSPC", "S&P500", "US Large Cap"}, {"^IXIC", "Nasdaq", "US Tech"}, {"^KS11", "KOSPI", "Korea"},
	{"^N225", "Nikkei", "Japan"}, {"KRW=X", "USD/KRW", "FX"}, {"^TNX", "US10Y", "Treasury"},
	{"^VIX", "VIX", "Volatility"}, {"BTC-USD", "BTC", "Crypto"}, {"NVDA", "NVDA", "NVIDIA"},
	{"005930.KS", "005930", "삼성전자"}, {"000660.KS", "000660", "SK하이닉스"},
	{"AAPL", "AAPL", "Apple"}, {"MSFT", "MSFT", "Microsoft"}, {"TSLA", "TSLA", "Tesla"},
	{"SOXX", "SOXX", "Semiconductor ETF"}, {"QQQ", "QQQ", "Nasdaq 100 ETF"}, {"TLT", "TLT", "Long Bond ETF"},
	{"SCHD", "SCHD", "Dividend ETF"},
}

func fetchLivePrices() ([]MarketPrice, error) {
	client := &http.Client{Timeout: 8 * time.Second}
	out := []MarketPrice{}
	observed := time.Now().Format(time.RFC3339)
	for _, item := range symbols {
		endpoint := "https://query1.finance.yahoo.com/v8/finance/chart/" + url.PathEscape(item.yahoo) + "?range=1d&interval=5m"
		req, _ := http.NewRequest(http.MethodGet, endpoint, nil)
		req.Header.Set("User-Agent", "MarketFlow-RetireOps/2.0")
		res, err := client.Do(req)
		if err != nil {
			return nil, err
		}
		var body struct {
			Chart struct {
				Result []struct {
					Meta struct {
						RegularMarketPrice float64 `json:"regularMarketPrice"`
						PreviousClose      float64 `json:"previousClose"`
					} `json:"meta"`
					Indicators struct {
						Quote []struct {
							Close []*float64 `json:"close"`
						} `json:"quote"`
					} `json:"indicators"`
				} `json:"result"`
			} `json:"chart"`
		}
		err = json.NewDecoder(res.Body).Decode(&body)
		res.Body.Close()
		if err != nil {
			return nil, err
		}
		if len(body.Chart.Result) == 0 {
			return nil, fmt.Errorf("missing market symbol: %s", item.yahoo)
		}
		meta := body.Chart.Result[0].Meta
		change := 0.0
		if meta.PreviousClose != 0 {
			change = (meta.RegularMarketPrice - meta.PreviousClose) / meta.PreviousClose * 100
		}
		if quotes := body.Chart.Result[0].Indicators.Quote; len(quotes) > 0 {
			storeSpark(item.id, quotes[0].Close)
		}
		out = append(out, MarketPrice{item.id, item.name, meta.RegularMarketPrice, change, 1000000, "yahoo-finance-chart", observed})
	}
	return out, nil
}

func dashboardPrices(fallback []MarketPrice) []MarketPrice {
	liveMu.Lock()
	defer liveMu.Unlock()
	if len(livePrices) > 0 && time.Since(liveFetchedAt) < 25*time.Second {
		return append([]MarketPrice(nil), livePrices...)
	}
	prices, err := fetchLivePrices()
	if err != nil || len(prices) == 0 {
		return fallback
	}
	livePrices = append([]MarketPrice(nil), prices...)
	liveFetchedAt = time.Now()
	return prices
}

func storeSpark(assetID string, closes []*float64) {
	points := make([]float64, 0, len(closes))
	for _, close := range closes {
		if close != nil {
			points = append(points, *close)
		}
	}
	if len(points) < 2 {
		return
	}
	if len(points) > 20 {
		points = points[len(points)-20:]
	}
	sparkMu.Lock()
	sparkCache[assetID] = points
	sparkMu.Unlock()
}

func sparkFor(price MarketPrice) []float64 {
	sparkMu.RLock()
	points := append([]float64(nil), sparkCache[price.AssetID]...)
	sparkMu.RUnlock()
	if len(points) >= 2 {
		return points
	}
	base := price.Price
	if base == 0 {
		base = 100
	}
	seed := 0
	for _, ch := range price.AssetID {
		seed += int(ch)
	}
	out := make([]float64, 8)
	for i := range out {
		wave := float64(((seed+i*7)%11)-5) / 500
		progress := float64(i-3) * price.ChangePercent / 700
		out[i] = base * (1 + wave + progress)
	}
	return out
}

func mockPrices() []MarketPrice {
	now := time.Now().Format(time.RFC3339)
	values := []MarketPrice{{"S&P500", "US Large Cap", 5304, 1.2, 1e6, "mock", now}, {"Nasdaq", "US Tech", 16920, 1.6, 1e6, "mock", now}, {"KOSPI", "Korea", 2724, .4, 1e6, "mock", now}, {"Nikkei", "Japan", 39102, .7, 1e6, "mock", now}, {"USD/KRW", "FX", 1360, .3, 1e6, "mock", now}, {"US10Y", "Treasury", 4.32, .4, 1e6, "mock", now}, {"VIX", "Volatility", 15.8, -.7, 1e6, "mock", now}, {"BTC", "Crypto", 68420, 2.4, 1e6, "mock", now}, {"005930", "삼성전자", 73500, 1.1, 1e6, "mock", now}, {"000660", "SK하이닉스", 208500, 2.8, 1e6, "mock", now}, {"NVDA", "NVIDIA", 1128.4, 3.8, 1e6, "mock", now}, {"AAPL", "Apple", 191.2, .9, 1e6, "mock", now}, {"MSFT", "Microsoft", 431.6, 1.1, 1e6, "mock", now}, {"TSLA", "Tesla", 178, -1.4, 1e6, "mock", now}, {"SOXX", "Semiconductor ETF", 240.8, 2.1, 1e6, "mock", now}, {"QQQ", "Nasdaq 100 ETF", 458.5, 1.5, 1e6, "mock", now}, {"TLT", "Long Bond ETF", 91.4, -.8, 1e6, "mock", now}, {"SCHD", "Dividend ETF", 78.6, .2, 1e6, "mock", now}, {"WTI", "Oil", 78.2, .1, 1e6, "mock", now}}
	return values
}
