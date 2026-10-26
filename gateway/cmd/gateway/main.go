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

	"github.com/acp-copilot/gateway/internal/api"
	"github.com/acp-copilot/gateway/internal/config"
	"github.com/acp-copilot/gateway/internal/database"
)

func main() {
	cfg := config.Load()

	db, err := database.Connect(cfg.MySQLDSN)
	if err != nil {
		log.Fatalf("连接 MySQL 失败: %v", err)
	}

	minioClient, err := minio.New(cfg.MinIOEndpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinIOAccessKey, cfg.MinIOSecretKey, ""),
		Secure: false,
	})
	if err != nil {
		log.Fatalf("连接 MinIO 失败: %v", err)
	}

	mqConn, err := amqp.Dial(cfg.RabbitMQURL)
	if err != nil {
		log.Fatalf("连接 RabbitMQ 失败: %v", err)
	}
	defer mqConn.Close()

	h := &api.Handler{
		DB:          db,
		JWTSecret:   cfg.JWTSecret,
		TokenTTL:    24 * time.Hour,
		AIEngineURL: cfg.AIEngineURL,
		Minio:       minioClient,
		MQConn:      mqConn,
		MinioBucket: cfg.MinIOBucket,
	}

	r := api.NewRouter(h, cfg.JWTSecret)
	log.Printf("gateway 监听 :%s", cfg.Port)
	if err := r.Run(":" + cfg.Port); err != nil {
		log.Fatalf("启动失败: %v", err)
	}
}
