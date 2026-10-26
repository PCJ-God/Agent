// Package auth 提供 JWT 签发与校验。
package auth

import (
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type Claims struct {
	UserID uint `json:"uid"`
	jwt.RegisteredClaims
}

// GenerateToken 签发一个包含 user_id 的 HS256 token。
func GenerateToken(secret string, userID uint, ttl time.Duration) (string, error) {
	claims := Claims{
		UserID: userID,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(ttl)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
	}
	return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(secret))
}

// ParseToken 校验 token 并返回其中的 user_id。
func ParseToken(secret, tokenStr string) (uint, error) {
	token, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(t *jwt.Token) (any, error) {
		return []byte(secret), nil
	})
	if err != nil {
		return 0, err
	}
	claims, ok := token.Claims.(*Claims)
	if !ok || !token.Valid {
		return 0, errors.New("invalid token")
	}
	return claims.UserID, nil
}
