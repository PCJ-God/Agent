// Package api 提供 HTTP 接口层。
package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
	amqp "github.com/rabbitmq/amqp091-go"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"

	"github.com/acp-copilot/gateway/internal/auth"
	"github.com/acp-copilot/gateway/internal/models"
)

type Handler struct {
	DB          *gorm.DB
	JWTSecret   string
	TokenTTL    time.Duration
	AIEngineURL string
	Minio       *minio.Client
	MQConn      *amqp.Connection
	MinioBucket string
}

func (h *Handler) Health(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "ok", "service": "gateway"})
}

type credentialsReq struct {
	Username string `json:"username" binding:"required,min=3,max=64"`
	Password string `json:"password" binding:"required,min=8,max=128"`
}

// Register 创建具名账号并返回 JWT。
func (h *Handler) Register(c *gin.Context) {
	var req credentialsReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to hash password"})
		return
	}

	user := models.User{Username: req.Username, PasswordHash: string(hash)}
	if err := h.DB.Create(&user).Error; err != nil {
		c.JSON(http.StatusConflict, gin.H{"error": "username already exists"})
		return
	}

	token, err := auth.GenerateToken(h.JWTSecret, user.ID, h.TokenTTL)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to issue token"})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"token": token, "user": user})
}

// Login 校验账号密码并签发新 JWT。
func (h *Handler) Login(c *gin.Context) {
	var req credentialsReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	var user models.User
	if err := h.DB.Where("username = ?", req.Username).First(&user).Error; err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid credentials"})
		return
	}
	if bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)) != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid credentials"})
		return
	}

	token, err := auth.GenerateToken(h.JWTSecret, user.ID, h.TokenTTL)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to issue token"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"token": token, "user": user})
}

// Me 返回当前登录用户信息（需鉴权）。
func (h *Handler) Me(c *gin.Context) {
	userID := c.GetUint("userID")
	var user models.User
	if err := h.DB.First(&user, userID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
		return
	}
	c.JSON(http.StatusOK, user)
}

// proxyToAIEngine 把请求流式转发到 AI 引擎的指定路径（SSE 透传，不解析 body）。
func (h *Handler) proxyToAIEngine(c *gin.Context, path string) {
	target, err := url.Parse(h.AIEngineURL)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "invalid ai engine url"})
		return
	}
	proxy := &httputil.ReverseProxy{
		Rewrite: func(pr *httputil.ProxyRequest) {
			pr.Out.URL.Scheme = target.Scheme
			pr.Out.URL.Host = target.Host
			pr.Out.URL.Path = path
		},
		FlushInterval: -1, // SSE：每次写立即 flush，不缓冲
	}
	proxy.ServeHTTP(c.Writer, c.Request)
}

// Chat 纯文本对话。
func (h *Handler) Chat(c *gin.Context) { h.proxyToAIEngine(c, "/chat") }

// ChatRag 检索增强对话。
func (h *Handler) ChatRag(c *gin.Context) { h.proxyToAIEngine(c, "/chat/rag") }

// RagIngest 摄入知识库文档。
func (h *Handler) RagIngest(c *gin.Context) { h.proxyToAIEngine(c, "/rag/ingest") }

// ChatAgent Agent 对话（RAG 工具 + 联网搜索）。
func (h *Handler) ChatAgent(c *gin.Context) { h.proxyToAIEngine(c, "/chat/agent") }

// ChatMemory 记忆对话（短期 + 长期记忆）。
func (h *Handler) ChatMemory(c *gin.Context) { h.proxyToAIEngine(c, "/chat/memory") }

// UploadFile 接收附件，存入 MinIO，并发布异步解析任务到 RabbitMQ。
func (h *Handler) UploadFile(c *gin.Context) {
	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "file 字段不能为空"})
		return
	}
	src, err := file.Open()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "读取文件失败"})
		return
	}
	defer src.Close()

	ctx := c.Request.Context()
	exists, err := h.Minio.BucketExists(ctx, h.MinioBucket)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "检查桶失败: " + err.Error()})
		return
	}
	if !exists {
		if err := h.Minio.MakeBucket(ctx, h.MinioBucket, minio.MakeBucketOptions{}); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "创建桶失败: " + err.Error()})
			return
		}
	}

	key := fmt.Sprintf("uploads/%s-%s", uuid.NewString(), file.Filename)
	if _, err := h.Minio.PutObject(ctx, h.MinioBucket, key, src, file.Size, minio.PutObjectOptions{
		ContentType: file.Header.Get("Content-Type"),
	}); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "上传 MinIO 失败: " + err.Error()})
		return
	}

	presigned, err := h.Minio.PresignedGetObject(ctx, h.MinioBucket, key, 24*time.Hour, nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "生成下载链接失败: " + err.Error()})
		return
	}

	msg, _ := json.Marshal(map[string]string{
		"object_key":   key,
		"download_url": presigned.String(),
		"filename":     file.Filename,
	})
	ch, err := h.MQConn.Channel()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "打开队列通道失败: " + err.Error()})
		return
	}
	defer ch.Close()
	if _, err := ch.QueueDeclare("doc_parse", true, false, false, false, nil); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "声明队列失败: " + err.Error()})
		return
	}
	if err := ch.Publish("", "doc_parse", false, false, amqp.Publishing{
		ContentType: "application/json",
		Body:        msg,
	}); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "发布任务失败: " + err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"object_key": key,
		"url":        presigned.String(),
		"status":     "queued",
	})
}
