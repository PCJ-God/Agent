package api

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"

	"github.com/acp-copilot/gateway/internal/auth"
)

// AuthMiddleware 校验 Bearer token，检查 JWT 黑名单，把 user_id/role/jti 放入上下文。
func AuthMiddleware(secret string, rdb *redis.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		header := c.GetHeader("Authorization")
		if !strings.HasPrefix(header, "Bearer ") {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing token"})
			return
		}
		claims, err := auth.ParseToken(secret, strings.TrimPrefix(header, "Bearer "))
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
			return
		}
		if rdb != nil {
			n, _ := rdb.Exists(c.Request.Context(), "blacklist:"+claims.JTI).Result()
			if n > 0 {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "token revoked"})
				return
			}
		}
		c.Set("userID", claims.UserID)
		c.Set("role", claims.Role)
		c.Set("jti", claims.JTI)
		c.Next()
	}
}

// AdminOnly 要求 role == admin。
func AdminOnly() gin.HandlerFunc {
	return func(c *gin.Context) {
		if c.GetString("role") != "admin" {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "admin only"})
			return
		}
		c.Next()
	}
}

// RateLimitMiddleware 每日固定窗口限流（按 user_id）。
func RateLimitMiddleware(rl *RateLimiter) gin.HandlerFunc {
	return func(c *gin.Context) {
		if rl == nil {
			c.Next()
			return
		}
		ok, used := rl.Allow(c.Request.Context(), c.GetUint("userID"))
		if !ok {
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{
				"error": "今日请求次数已达上限",
				"used":  used,
			})
			return
		}
		c.Next()
	}
}
