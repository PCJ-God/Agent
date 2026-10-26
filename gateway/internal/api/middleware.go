package api

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"github.com/acp-copilot/gateway/internal/auth"
)

// AuthMiddleware 校验 Authorization: Bearer <token>，把 user_id 放入上下文。
func AuthMiddleware(secret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		header := c.GetHeader("Authorization")
		if !strings.HasPrefix(header, "Bearer ") {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing token"})
			return
		}
		userID, err := auth.ParseToken(secret, strings.TrimPrefix(header, "Bearer "))
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
			return
		}
		c.Set("userID", userID)
		c.Next()
	}
}
