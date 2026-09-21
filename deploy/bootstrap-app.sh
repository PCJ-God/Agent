#!/usr/bin/env bash
#
# 应用侧一次性初始化 —— 在云服务器上（Ubuntu）以「有 sudo 权限的普通用户」运行。
#
#   bash deploy/bootstrap-app.sh            # 默认分支 multi-agent
#   bash deploy/bootstrap-app.sh <分支名>
#
# 设计原则：
#   * 幂等 —— 已完成的步骤会跳过，可以反复跑
#   * 失败即停（set -e），不会留下一半的状态却继续往下走
#   * 每一步都打印结论，方便定位是哪一步不对
#   * 只碰「应用自己」的范围：不自动改 nginx / 证书 / 防火墙配置
#
# 未做端到端实测（写脚本的机器上没有目标服务器），只做过 bash 语法检查。
# 因此它刻意做得保守：不覆盖已有 .env、不删任何目录、不碰网络配置。

set -euo pipefail

BRANCH="${1:-multi-agent}"
APP_DIR=/opt/agent
APP_USER=agent
REPO_URL=https://github.com/PCJ-God/Agent.git
PIP_INDEX=https://mirrors.cloud.tencent.com/pypi/simple

step() { printf '\n\033[1m==== %s ====\033[0m\n' "$*"; }
info() { printf '     %s\n' "$*"; }
fail() { printf '\n!! %s\n' "$*" >&2; exit 1; }

step "0/6 前置检查"
[ "$(id -u)" -ne 0 ] || fail "不要直接用 root 跑这个脚本。用带 sudo 的普通用户（腾讯云 Ubuntu 一般是 ubuntu）。"
command -v sudo >/dev/null || fail "找不到 sudo"
info "Python: $(python3 --version 2>&1 || echo '未安装')"
info "分支:   $BRANCH"
info "目录:   $APP_DIR"

step "1/6 系统依赖"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv git
command -v git >/dev/null || fail "git 安装失败"

step "2/6 服务账号与应用目录"
if id "$APP_USER" >/dev/null 2>&1; then
  info "用户 $APP_USER 已存在，跳过创建"
else
  # 家目录故意不用 $APP_DIR：useradd -m 会往目录里写 .bashrc 等，
  # 之后 git clone 到非空目录会直接失败。
  sudo useradd -r -m -d "/home/$APP_USER" -s /bin/bash "$APP_USER"
  info "已创建用户 $APP_USER（家目录 /home/$APP_USER）"
fi
sudo mkdir -p "$APP_DIR"
sudo chown "$APP_USER:$APP_USER" "$APP_DIR"

step "3/6 拉取代码（分支 $BRANCH）"
if [ -d "$APP_DIR/.git" ]; then
  info "已是 git 仓库，改为 git pull"
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
else
  if [ -n "$(ls -A "$APP_DIR" 2>/dev/null || true)" ]; then
    fail "$APP_DIR 非空且不是 git 仓库。先清理它，或改脚本里的 APP_DIR。"
  fi
  sudo -u "$APP_USER" git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
[ -f "$APP_DIR/scripts/run_server.py" ] || fail "clone 结果不对：找不到 $APP_DIR/scripts/run_server.py"
[ -f "$APP_DIR/deploy/agent.service" ] || fail "clone 结果不对：找不到 deploy/agent.service（分支选错了吗？默认分支 main 上没有它）"
info "代码已就位"

step "4/6 虚拟环境与依赖（约 1.9 GB，走腾讯云镜像）"
[ -x "$APP_DIR/.venv/bin/python" ] || sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
# 关键：必须配合 constraints.txt 钉住实测版本。不加 -c 会装到
# agentscope 2.x / openai 3.x / mem0ai 2.x —— 从未验证过的组合。
[ -f "$APP_DIR/constraints.txt" ] || fail "找不到 $APP_DIR/constraints.txt"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -i "$PIP_INDEX" \
  -c "$APP_DIR/constraints.txt" -r "$APP_DIR/requirements.txt"
info "依赖安装完成"

step "5/6 .env"
if [ -f "$APP_DIR/.env" ]; then
  info "$APP_DIR/.env 已存在，保持原样不动"
else
  sudo -u "$APP_USER" cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  info "已从模板生成 $APP_DIR/.env —— 需要你填 DASHSCOPE_API_KEY"
fi
sudo chmod 600 "$APP_DIR/.env"

# 用项目自己的导入链做验证：会把 agentscope / mem0 / qdrant 全部拉起来，
# 比单独 import 几个包更能反映真实情况。不需要 API Key 参与。
info "验证依赖链…"
sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && ./.venv/bin/python -c 'import src.config, src.orchestration.hierarchical'"
info "依赖链导入 OK"

step "6/6 检查 skills"
SKILL_N=$(find "$APP_DIR/skills" -name SKILL.md 2>/dev/null | wc -l | tr -d ' ')
info "找到 $SKILL_N 个 SKILL.md"
if [ "$SKILL_N" -lt 2 ]; then
  printf '\n!! 注意：只有 %s 个 skill。\n' "$SKILL_N"
  info "skills/frontend-design 没有进版本库（.gitignore 的历史遗留），需要从本地传过来："
  info "  scp -r <本地>/skills/frontend-design ubuntu@<服务器IP>:/tmp/"
  info "  然后: sudo mv /tmp/frontend-design $APP_DIR/skills/ && sudo chown -R $APP_USER:$APP_USER $APP_DIR/skills"
fi

cat <<NEXT

============================================================
应用侧初始化完成。接下来（顺序不要跳）：

 1) 填 API Key
      sudo -u $APP_USER vi $APP_DIR/.env
   只需要改 DASHSCOPE_API_KEY。HOST / PORT / FORWARDED_ALLOW_IPS 的默认值就是对的。
   QDRANT_URL 留空即可（单进程部署不需要 Qdrant server）。

 2) 先手动前台跑一次 —— 把「应用有问题」和「服务配置有问题」分开
      sudo -u $APP_USER bash -c 'cd $APP_DIR && ./.venv/bin/python scripts/run_server.py'
    另开一个终端验证：
      curl -s http://127.0.0.1:8000/health      # 期望 {"status":"ok",...}
    看到 ok 后回前台 Ctrl+C 停掉。

 3) 装成系统服务
      sudo cp $APP_DIR/deploy/agent.service /etc/systemd/system/agent.service
      sudo systemctl daemon-reload
      sudo systemctl enable --now agent
      systemctl status agent --no-pager

 4) nginx + HTTPS —— 这一步有顺序要求（证书 / 80 端口互为前提），
    照 docs/DEPLOY.md 的「第 0 步」+「方案 A1 / 路线一」走，不要凭感觉改顺序。
============================================================
NEXT
