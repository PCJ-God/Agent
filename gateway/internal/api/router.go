package api

import "github.com/gin-gonic/gin"

// NewRouter 装配全部路由与中间件，返回可直接运行的 gin.Engine。
func NewRouter(h *Handler, jwtSecret string) *gin.Engine {
	r := gin.Default()
	r.Use(MetricsMiddleware())
	r.GET("/health", h.Health)
	r.GET("/metrics", Metrics)

	v1 := r.Group("/api")
	v1.POST("/auth/register", h.Register)
	v1.POST("/auth/login", h.Login)

	authed := v1.Group("")
	authed.Use(AuthMiddleware(jwtSecret, h.Redis))
	authed.GET("/auth/me", h.Me)
	authed.POST("/auth/logout", h.Logout)

	// 昂贵接口加每日限流
	limited := authed.Group("")
	limited.Use(RateLimitMiddleware(h.Limiter))
	limited.POST("/assistant", h.Assistant)
	limited.POST("/files/upload", h.UploadFiles)
	limited.GET("/files/status", h.ParseStatus)

	admin := authed.Group("/admin")
	admin.Use(AdminOnly())
	admin.POST("/kb/add", h.AdminKBAdd)
	admin.POST("/reindex", h.Reindex)

	return r
}
