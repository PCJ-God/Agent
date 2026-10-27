package api

import "github.com/gin-gonic/gin"

// NewRouter 装配全部路由与中间件，返回可直接运行的 gin.Engine。
func NewRouter(h *Handler, jwtSecret, internalToken string) *gin.Engine {
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

	// 飞书绑定（Web 端，JWT 鉴权）
	bind := authed.Group("/bind/feishu")
	bind.POST("", h.BindFeishu)
	bind.GET("/status", h.FeishuBindStatus)
	bind.POST("/unbind", h.UnbindFeishu)

	// 服务间内部接口（feishu-adapter 专用，走 X-Internal-Token）
	internal := v1.Group("/internal/feishu")
	internal.Use(InternalTokenMiddleware(internalToken))
	internal.POST("/bind-code", h.FeishuBindCode)
	internal.POST("/token", h.FeishuToken)

	return r
}
