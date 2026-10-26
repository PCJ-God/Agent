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
	authed.Use(AuthMiddleware(jwtSecret))
	authed.GET("/auth/me", h.Me)
	authed.POST("/chat", h.Chat)
	authed.POST("/chat/rag", h.ChatRag)
	authed.POST("/chat/agent", h.ChatAgent)
	authed.POST("/chat/memory", h.ChatMemory)
	authed.POST("/rag/ingest", h.RagIngest)
	authed.POST("/files/upload", h.UploadFile)

	return r
}
