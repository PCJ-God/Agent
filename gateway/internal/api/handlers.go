// Package api 提供 HTTP 接口层。
package api

import (
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redis/go-redis/v9"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"

	"github.com/acp-copilot/gateway/internal/auth"
	"github.com/acp-copilot/gateway/internal/models"
	pb "github.com/acp-copilot/gateway/gen/assistant/v1"
)

type Handler struct {
	DB          *gorm.DB
	JWTSecret   string
	TokenTTL    time.Duration
	Minio       *minio.Client
	MQConn      *amqp.Connection
	MinioBucket string
	Redis       *redis.Client
	AIStub      pb.AssistantServiceClient
	Limiter     *RateLimiter
	MaxFileMB   int64
	MaxFiles    int
	MaxTotalMB  int64
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

	user := models.User{Username: req.Username, PasswordHash: string(hash), Role: "user"}
	if err := h.DB.Create(&user).Error; err != nil {
		c.JSON(http.StatusConflict, gin.H{"error": "username already exists"})
		return
	}

	token, _, err := auth.GenerateToken(h.JWTSecret, user.ID, user.Role, h.TokenTTL)
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

	token, _, err := auth.GenerateToken(h.JWTSecret, user.ID, user.Role, h.TokenTTL)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to issue token"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"token": token, "user": user})
}

// Me 返回当前登录用户（含 role，前端据此切换管理员界面）。
func (h *Handler) Me(c *gin.Context) {
	userID := c.GetUint("userID")
	var user models.User
	if err := h.DB.First(&user, userID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
		return
	}
	c.JSON(http.StatusOK, user)
}

// Logout 把当前 token 的 jti 加入 Redis 黑名单，TTL 覆盖 token 剩余寿命。
func (h *Handler) Logout(c *gin.Context) {
	jti := c.GetString("jti")
	if jti != "" && h.Redis != nil {
		h.Redis.Set(c.Request.Context(), "blacklist:"+jti, "1", h.TokenTTL)
	}
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

// Assistant 统一对话入口：把请求转给 ai-engine 的 gRPC 流，再转成 SSE 推给前端。
func (h *Handler) Assistant(c *gin.Context) {
	var req struct {
		Message   string   `json:"message" binding:"required"`
		SessionID string   `json:"session_id"`
		TaskIDs   []string `json:"task_ids"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if len(req.TaskIDs) > h.MaxFiles {
		c.JSON(http.StatusBadRequest, gin.H{"error": "上传文件太多"})
		return
	}
	userID := c.GetUint("userID")

	stream, err := h.AIStub.Chat(c.Request.Context(), &pb.ChatRequest{
		UserId:    strconv.FormatUint(uint64(userID), 10),
		SessionId: req.SessionID,
		Message:   req.Message,
		TaskIds:   req.TaskIDs,
	})
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "ai-engine 不可用: " + err.Error()})
		return
	}

	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	c.Header("X-Accel-Buffering", "no")

	flusher, _ := c.Writer.(http.Flusher)
	for {
		ev, err := stream.Recv()
		if err == io.EOF {
			return
		}
		if err != nil {
			writeSSE(c, gin.H{"type": "error", "text": err.Error(), "done": true})
			return
		}
		writeSSE(c, eventToH(ev))
		if flusher != nil {
			flusher.Flush()
		}
		if ev.GetDone() {
			return
		}
	}
}

func eventToH(ev *pb.ChatEvent) gin.H {
	sources := make([]gin.H, 0, len(ev.GetSources()))
	for _, s := range ev.GetSources() {
		sources = append(sources, gin.H{
			"source":      s.GetSource(),
			"header_path": s.GetHeaderPath(),
			"score":       s.GetScore(),
		})
	}
	return gin.H{
		"type":    ev.GetType(),
		"text":    ev.GetText(),
		"sources": sources,
		"done":    ev.GetDone(),
	}
}

func writeSSE(c *gin.Context, payload gin.H) {
	b, _ := json.Marshal(payload)
	fmt.Fprintf(c.Writer, "data: %s\n\n", b)
}

// Reindex 管理员重灌课程知识库（经 gRPC 转给 ai-engine）。
func (h *Handler) Reindex(c *gin.Context) {
	var req struct {
		DocsDir string `json:"docs_dir"`
	}
	_ = c.ShouldBindJSON(&req)
	resp, err := h.AIStub.Reindex(c.Request.Context(), &pb.ReindexRequest{DocsDir: req.DocsDir})
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ingested": resp.GetIngested(), "sources": resp.GetSources()})
}

// UploadFiles 用户上传附件（多文件）：落 MinIO → 入队解析 → 返回 task_ids。
func (h *Handler) UploadFiles(c *gin.Context) {
	h.uploadFiles(c, c.DefaultQuery("task_type", "chat"))
}

// AdminKBAdd 管理员上传知识库文档：解析后经 gRPC 写入课程知识库。
func (h *Handler) AdminKBAdd(c *gin.Context) {
	h.uploadFiles(c, "ingest")
}

func (h *Handler) uploadFiles(c *gin.Context, taskType string) {
	form, err := c.MultipartForm()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请用 multipart/form-data 上传"})
		return
	}
	files := form.File["files"]
	if len(files) == 0 {
		files = form.File["file"]
	}
	if len(files) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "缺少文件"})
		return
	}
	if len(files) > h.MaxFiles {
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"error": "上传文件太多"})
		return
	}
	var total int64
	for _, f := range files {
		total += f.Size
		if f.Size > h.MaxFileMB<<20 {
			c.JSON(http.StatusRequestEntityTooLarge, gin.H{"error": "上传文件太大"})
			return
		}
	}
	if total > h.MaxTotalMB<<20 {
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"error": "上传数据总量太大"})
		return
	}

	taskIDs := make([]string, 0, len(files))
	for _, f := range files {
		tid, err := h.uploadOne(c, f, taskType)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		taskIDs = append(taskIDs, tid)
	}
	c.JSON(http.StatusOK, gin.H{"task_ids": taskIDs, "status": "queued"})
}

func (h *Handler) uploadOne(c *gin.Context, fh *multipart.FileHeader, taskType string) (string, error) {
	src, err := fh.Open()
	if err != nil {
		return "", fmt.Errorf("读取文件失败: %w", err)
	}
	defer src.Close()

	ctx := c.Request.Context()
	exists, err := h.Minio.BucketExists(ctx, h.MinioBucket)
	if err != nil {
		return "", fmt.Errorf("检查桶失败: %w", err)
	}
	if !exists {
		if err := h.Minio.MakeBucket(ctx, h.MinioBucket, minio.MakeBucketOptions{}); err != nil {
			return "", fmt.Errorf("创建桶失败: %w", err)
		}
	}

	key := fmt.Sprintf("uploads/%s-%s", uuid.NewString(), fh.Filename)
	if _, err := h.Minio.PutObject(ctx, h.MinioBucket, key, src, fh.Size, minio.PutObjectOptions{
		ContentType: fh.Header.Get("Content-Type"),
	}); err != nil {
		return "", fmt.Errorf("上传 MinIO 失败: %w", err)
	}

	presigned, err := h.Minio.PresignedGetObject(ctx, h.MinioBucket, key, 24*time.Hour, nil)
	if err != nil {
		return "", fmt.Errorf("生成下载链接失败: %w", err)
	}

	taskID := uuid.NewString()
	msg, _ := json.Marshal(map[string]string{
		"task_id":      taskID,
		"object_key":   key,
		"download_url": presigned.String(),
		"filename":     fh.Filename,
		"task_type":    taskType,
	})
	if err := h.publishParse(msg); err != nil {
		return "", err
	}
	return taskID, nil
}

func (h *Handler) publishParse(msg []byte) error {
	ch, err := h.MQConn.Channel()
	if err != nil {
		return fmt.Errorf("打开队列通道失败: %w", err)
	}
	defer ch.Close()
	if _, err := ch.QueueDeclare("doc_parse", true, false, false, false, nil); err != nil {
		return fmt.Errorf("声明队列失败: %w", err)
	}
	if err := ch.Publish("", "doc_parse", false, false, amqp.Publishing{
		ContentType: "application/json",
		Body:        msg,
	}); err != nil {
		return fmt.Errorf("发布任务失败: %w", err)
	}
	return nil
}

// ParseStatus 查询解析任务状态（前端轮询，直到 done 再发起对话）。
func (h *Handler) ParseStatus(c *gin.Context) {
	ids := c.QueryArray("task_id")
	if len(ids) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "缺少 task_id"})
		return
	}
	statuses := gin.H{}
	for _, id := range ids {
		st, err := h.Redis.Get(c.Request.Context(), "parse:status:"+id).Result()
		if err != nil || st == "" {
			st = "pending"
		}
		statuses[id] = st
	}
	c.JSON(http.StatusOK, gin.H{"statuses": statuses})
}
