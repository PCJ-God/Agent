// Package models 定义核心业务表结构。
// Phase 1 先落地 User / Session / Message 三张表；
// Agent、Attachment 在后续阶段补（见 README 存储设计）。
package models

import "time"

type User struct {
	ID           uint      `gorm:"primaryKey" json:"id"`
	Username     string    `gorm:"uniqueIndex;size:64;not null" json:"username"`
	PasswordHash string    `gorm:"size:255;not null" json:"-"`
	CreatedAt    time.Time `json:"created_at"`
}

type Session struct {
	ID        uint      `gorm:"primaryKey" json:"id"`
	UserID    uint      `gorm:"index;not null" json:"user_id"`
	SessionID string    `gorm:"uniqueIndex;size:64;not null" json:"session_id"`
	Title     string    `gorm:"size:255" json:"title"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type Message struct {
	ID          uint      `gorm:"primaryKey" json:"id"`
	UserID      uint      `gorm:"index;not null" json:"user_id"`
	SessionID   string    `gorm:"index;size:64;not null" json:"session_id"`
	Role        string    `gorm:"size:16;not null" json:"role"`      // user / assistant
	Content     string    `gorm:"type:text" json:"content"`
	Source      string    `gorm:"size:16" json:"source"`             // local / web / mixed
	SearchQuery string    `gorm:"size:255" json:"search_query"`      // 联网搜索词（无则空）
	CreatedAt   time.Time `json:"created_at"`
}
