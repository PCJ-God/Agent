package api

import (
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"

	"github.com/gin-gonic/gin"
)

var (
	reqCounters   = map[string]int64{}
	reqCountersMu sync.Mutex
)

// MetricsMiddleware 统计每个路由的累计请求数（供 Prometheus 抓取）。
func MetricsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		path := c.FullPath()
		if path == "" {
			path = c.Request.URL.Path
		}
		reqCountersMu.Lock()
		reqCounters[path]++
		reqCountersMu.Unlock()
		c.Next()
	}
}

// Metrics 输出 Prometheus text 格式指标（手写，不引第三方依赖）。
func Metrics(c *gin.Context) {
	reqCountersMu.Lock()
	keys := make([]string, 0, len(reqCounters))
	for k := range reqCounters {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var sb strings.Builder
	sb.WriteString("# HELP http_requests_total 累计 HTTP 请求数\n")
	sb.WriteString("# TYPE http_requests_total counter\n")
	for _, k := range keys {
		sb.WriteString("http_requests_total{path=\"" + k + "\"} " + strconv.FormatInt(reqCounters[k], 10) + "\n")
	}
	reqCountersMu.Unlock()

	c.Data(http.StatusOK, "text/plain; version=0.0.4; charset=utf-8", []byte(sb.String()))
}
