# 生成 gRPC 桩代码（Go + Python）
$ErrorActionPreference = 'Stop'

New-Item -ItemType Directory -Force -Path gateway/gen/assistant/v1 | Out-Null
New-Item -ItemType Directory -Force -Path ai-engine/gen | Out-Null

$gopath = (go env GOPATH).Trim()
$env:Path = "$gopath\bin;$env:Path"

# Go 桩
protoc -I proto `
  --go_out=gateway/gen/assistant/v1 --go_opt=paths=source_relative `
  --go-grpc_out=gateway/gen/assistant/v1 --go-grpc_opt=paths=source_relative `
  proto/assistant.proto
if ($LASTEXITCODE -ne 0) { throw "go codegen failed: $LASTEXITCODE" }

# Python 桩
python -m grpc_tools.protoc -I proto `
  --python_out=ai-engine/gen `
  --grpc_python_out=ai-engine/gen `
  proto/assistant.proto
if ($LASTEXITCODE -ne 0) { throw "python codegen failed: $LASTEXITCODE" }

# 修正扁平 import：gen 作为子包导入时，grpc 生成文件里的 `import assistant_pb2`
# 无法解析，需改为包内导入。
$grpcFile = 'ai-engine/gen/assistant_pb2_grpc.py'
(Get-Content $grpcFile -Raw) `
  -replace '(?m)^import assistant_pb2 as assistant__pb2$',
           'from gen import assistant_pb2 as assistant__pb2' |
  Set-Content -NoNewline -Encoding utf8 $grpcFile

Write-Output "codegen ok"
