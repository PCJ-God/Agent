// Package api — Redis 每日固定窗口限流。
package api

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

// INCR + 首次设置过期（原子 Lua），窗口为自然日。
const rateLimitScript = `
local n = redis.call('INCR', KEYS[1])
if n == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return n
`

type RateLimiter struct {
	rdb    *redis.Client
	perDay int64
}

func NewRateLimiter(rdb *redis.Client, perDay int64) *RateLimiter {
	return &RateLimiter{rdb: rdb, perDay: perDay}
}

func (rl *RateLimiter) Allow(ctx context.Context, userID uint) (bool, int64) {
	now := time.Now()
	key := fmt.Sprintf("ratelimit:%d:%s", userID, now.Format("2006-01-02"))
	endOfDay := time.Date(now.Year(), now.Month(), now.Day()+1, 0, 0, 0, 0, now.Location())
	ttl := int64(time.Until(endOfDay).Seconds())
	if ttl <= 0 {
		ttl = 86400
	}
	n, err := rl.rdb.Eval(ctx, rateLimitScript, []string{key}, ttl).Int64()
	if err != nil {
		// Redis 故障时放行，避免把正常流量拒之门外
		return true, 0
	}
	return n <= rl.perDay, n
}
