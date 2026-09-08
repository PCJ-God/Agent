# 部署指南

## 本地开发环境

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd Agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制环境配置模板
cp .env.example .env

# 编辑 .env 文件,填入你的 DashScope API Key
# 获取 API Key: https://bailian.console.aliyun.com/
```

### 3. 运行示例

```bash
# 运行基础工具调用示例
python examples/basic_tool_call.py

# 运行 MCP 集成示例
python examples/mcp_integration.py

# 运行多Agent协作示例
python examples/multi_agent_collaboration.py
```

### 4. 运行测试

```bash
# 运行单元测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=src --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html  # Mac
# 或
start htmlcov/index.html  # Windows
```

## 生产环境部署

### Docker 部署

#### 1. 创建 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源代码
COPY . .

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 启动命令
CMD ["python", "-m", "src.cli"]
```

#### 2. 创建 docker-compose.yml

```yaml
version: '3.8'

services:
  agent:
    build: .
    environment:
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data
    restart: unless-stopped

  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile.mcp
    environment:
      - LOG_LEVEL=INFO
    ports:
      - "8080:8080"
    restart: unless-stopped
```

#### 3. 构建和运行

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f agent
```

### Kubernetes 部署

#### 1. 创建 ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-config
data:
  LOG_LEVEL: "INFO"
  MEMORY_STORAGE_PATH: "/data/memory"
```

#### 2. 创建 Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: agent-secrets
type: Opaque
data:
  DASHSCOPE_API_KEY: <base64-encoded-api-key>
```

#### 3. 创建 Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-deployment
spec:
  replicas: 3
  selector:
    matchLabels:
      app: intelligent-teaching-agent
  template:
    metadata:
      labels:
        app: intelligent-teaching-agent
    spec:
      containers:
      - name: agent
        image: intelligent-teaching-agent:latest
        envFrom:
        - configMapRef:
            name: agent-config
        - secretRef:
            name: agent-secrets
        volumeMounts:
        - name: data
          mountPath: /app/data
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: agent-data-pvc
```

## 监控和日志

### 日志配置

系统使用 Loguru 进行日志管理,支持以下级别:

- `DEBUG`: 调试信息 (开发环境)
- `INFO`: 一般信息 (生产环境)
- `WARNING`: 警告信息
- `ERROR`: 错误信息

### 性能监控

关键指标:

- 工具调用响应时间
- Agent 循环次数
- 内存使用量
- 错误率

## 故障排查

### 常见问题

#### 1. API Key 无效

**症状**: 调用大模型时返回 401 错误

**解决方案**:
- 检查 `.env` 文件中的 `DASHSCOPE_API_KEY` 是否正确
- 确认 API Key 已激活且有足够额度
- 前往 https://bailian.console.aliyun.com/ 检查 API Key 状态

#### 2. MCP Server 连接失败

**症状**: Agent 启动时报 MCP 连接错误

**解决方案**:
- 检查 MCP Server 进程是否正在运行
- 确认 `stdio` 模式下脚本路径正确
- 确认 `Streamable HTTP` 模式下 URL 和 Header 正确

#### 3. 工具调用失败

**症状**: Agent 无法调用工具或参数错误

**解决方案**:
- 检查工具函数是否正确注册到 Toolkit
- 检查工具的文档字符串 (docstring) 是否清晰
- 查看日志中的工具调用详情

## 性能优化

### 1. 并发优化

- 使用 `asyncio.gather()` 并行执行独立任务
- 设置合理的并发上限,避免资源耗尽

### 2. 缓存优化

- 缓存常见的搜索结果
- 设置合理的缓存过期时间

### 3. 资源限制

- 设置 Agent 最大循环次数 (`max_iters`)
- 设置工具调用超时时间
- 限制记忆存储大小

## 安全建议

### 1. API Key 管理

- 使用环境变量或密钥管理服务 (如 AWS Secrets Manager)
- 不要将 API Key 提交到代码仓库
- 定期轮换 API Key

### 2. 工具权限

- 为不同 Agent 配置不同的工具访问权限
- 对敏感工具添加鉴权检查

### 3. 数据隐私

- 不存储用户敏感信息
- 对记忆数据进行脱敏处理
- 定期清理过期的记忆数据

## 相关资源

- [阿里云 DashScope 文档](https://help.aliyun.com/zh/dashscope/)
- [AgentScope 官方文档](https://github.com/agentscope-ai/agentscope)
- [MCP 协议规范](https://modelcontextprotocol.io/specification)
