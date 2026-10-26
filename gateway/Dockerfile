# 构建阶段
FROM golang:1.27-alpine AS builder
ENV GOPROXY=https://goproxy.cn,direct
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /gateway ./cmd/gateway

# 运行阶段
FROM alpine:3.19
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories \
    && apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /gateway .
EXPOSE 8080
ENTRYPOINT ["./gateway"]
