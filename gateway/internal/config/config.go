// Package config 负责从环境变量加载网关配置。
// 默认值与本项目 docker-compose.yml 里的服务名/端口保持一致。
package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	Port           string
	MySQLDSN       string
	RedisAddr      string
	RabbitMQURL    string
	AIGRPCAddr     string
	JWTSecret      string
	FeishuAdapterToken string
	TokenTTL       time.Duration
	RateLimitPerDay int64
	AdminUsername  string
	AdminPassword  string
	MaxFileSizeMB  int64
	MaxFiles       int
	MaxTotalMB     int64
	MinIOEndpoint  string
	MinIOAccessKey string
	MinIOSecretKey string
	MinIOBucket    string
}

func Load() *Config {
	return &Config{
		Port:           getenv("PORT", "8080"),
		MySQLDSN:       getenv("MYSQL_DSN", "acp:acp123@tcp(127.0.0.1:3306)/acp?charset=utf8mb4&parseTime=True&loc=Local"),
		RedisAddr:      getenv("REDIS_ADDR", "127.0.0.1:6379"),
		RabbitMQURL:    getenv("RABBITMQ_URL", "amqp://acp:acp@127.0.0.1:5672/"),
		AIGRPCAddr:     getenv("AI_GRPC_ADDR", "ai-engine:50051"),
		JWTSecret:      getenv("JWT_SECRET", "dev-secret-change-me"),
		FeishuAdapterToken: getenv("FEISHU_ADAPTER_TOKEN", ""),
		TokenTTL:       24 * time.Hour,
		RateLimitPerDay: int64(getenvInt("RATE_LIMIT_PER_DAY", 20)),
		AdminUsername:  getenv("ADMIN_USERNAME", "admin"),
		AdminPassword:  getenv("ADMIN_PASSWORD", "admin123456"),
		MaxFileSizeMB:  int64(getenvInt("MAX_FILE_SIZE_MB", 10)),
		MaxFiles:       getenvInt("MAX_FILES", 5),
		MaxTotalMB:     int64(getenvInt("MAX_TOTAL_MB", 30)),
		MinIOEndpoint:  getenv("MINIO_ENDPOINT", "minio:9000"),
		MinIOAccessKey: getenv("MINIO_ACCESS_KEY", "acpadmin"),
		MinIOSecretKey: getenv("MINIO_SECRET_KEY", "acpadmin123"),
		MinIOBucket:    getenv("MINIO_BUCKET", "acp-docs"),
	}
}

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getenvInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}
