// Package config 负责从环境变量加载网关配置。
// 默认值与本项目 docker-compose.yml 里的服务名/端口保持一致，
// 因此「docker compose up」时无需额外配置即可连通各组件。
package config

import "os"

type Config struct {
	Port           string
	MySQLDSN       string
	RedisAddr      string
	RabbitMQURL    string
	AIEngineURL    string
	JWTSecret      string
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
		AIEngineURL:    getenv("AI_ENGINE_URL", "http://127.0.0.1:8000"),
		JWTSecret:      getenv("JWT_SECRET", "dev-secret-change-me"),
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
