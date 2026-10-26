// Package database 负责建立 MySQL 连接并自动迁移表结构。
package database

import (
	"github.com/acp-copilot/gateway/internal/models"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

// Connect 建立连接并迁移表结构。迁移失败会返回错误，由调用方决定退出。
func Connect(dsn string) (*gorm.DB, error) {
	db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{})
	if err != nil {
		return nil, err
	}
	if err := db.AutoMigrate(
		&models.User{},
		&models.Session{},
		&models.Message{},
	); err != nil {
		return nil, err
	}
	return db, nil
}
