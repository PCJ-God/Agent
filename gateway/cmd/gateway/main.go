// ACP Copilot — Go 网关入口。
// 按标准 Go 项目布局，入口只做「装配」：加载配置、连库、建路由、启动。
// 具体路由与中间件见 internal/api。
package main

import (
	"log"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redis/go-redis/v9"
	"golang.org/x/crypto/bcrypt"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"gorm.io/gorm"

	"github.com/acp-copilot/gateway/internal/api"
	"github.com/acp-copilot/gateway/internal/config"
	"github.com/acp-copilot/gateway/internal/database"
	"github.com/acp-copilot/gateway/internal/models"
	pb "github.com/acp-copilot/gateway/gen/assistant/v1"
)

func main() {
	cfg := config.Load()

	db, err := database.Connect(cfg.MySQLDSN)
	if err != nil {
		log.Fatalf("连接 MySQL 失败: %v", err)
	}
	seedAdmin(db, cfg.AdminUsername, cfg.AdminPassword)

	minioClient, err := minio.New(cfg.MinIOEndpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinIOAccessKey, cfg.MinIOSecretKey, ""),
		Secure: false,
	})
	if err != nil {
		log.Fatalf("连接 MinIO 失败: %v", err)
	}

	mqConn, err := dialRabbit(cfg.RabbitMQURL)
	if err != nil {
		log.Fatalf("连接 RabbitMQ 失败: %v", err)
	}
	defer mqConn.Close()

	rdb := redis.NewClient(&redis.Options{Addr: cfg.RedisAddr})

	conn, err := grpc.NewClient(cfg.AIGRPCAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("连接 ai-engine 失败: %v", err)
	}
	defer conn.Close()

	h := &api.Handler{
		DB:          db,
		JWTSecret:   cfg.JWTSecret,
		TokenTTL:    cfg.TokenTTL,
		Minio:       minioClient,
		MQConn:      mqConn,
		MinioBucket: cfg.MinIOBucket,
		Redis:       rdb,
		AIStub:      pb.NewAssistantServiceClient(conn),
		Limiter:     api.NewRateLimiter(rdb, cfg.RateLimitPerDay),
		MaxFileMB:   cfg.MaxFileSizeMB,
		MaxFiles:    cfg.MaxFiles,
		MaxTotalMB:  cfg.MaxTotalMB,
	}

	r := api.NewRouter(h, cfg.JWTSecret)
	log.Printf("gateway 监听 :%s", cfg.Port)
	if err := r.Run(":" + cfg.Port); err != nil {
		log.Fatalf("启动失败: %v", err)
	}
}

// dialRabbit 带重试地建立 RabbitMQ 连接。rabbitmq 健康检查通过时 AMQP 端口
// 可能尚未就绪，冷启动时重试几次避免 gateway 反复崩溃重启。
func dialRabbit(url string) (*amqp.Connection, error) {
	var err error
	for i := 1; i <= 10; i++ {
		conn, derr := amqp.Dial(url)
		if derr == nil {
			return conn, nil
		}
		err = derr
		log.Printf("连接 RabbitMQ 失败（%d/10）: %v，3s 后重试", i, derr)
		time.Sleep(3 * time.Second)
	}
	return nil, err
}

// seedAdmin 首次启动时创建一个管理员账号（幂等：已存在则跳过）。
func seedAdmin(db *gorm.DB, username, password string) {	var count int64
	db.Model(&models.User{}).Where("role = ?", "admin").Count(&count)
	if count > 0 {
		return
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		log.Fatalf("生成管理员密码哈希失败: %v", err)
	}
	if err := db.Create(&models.User{Username: username, PasswordHash: string(hash), Role: "admin"}).Error; err != nil {
		log.Fatalf("创建管理员失败: %v", err)
	}
	log.Printf("已创建管理员账号: %s", username)
}
