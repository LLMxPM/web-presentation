#!/usr/bin/env bash
# 文件功能：在 CI 中可靠拉取并启动 E2E 所需的 PostgreSQL 与 Redis 依赖。

set -euo pipefail

readonly compose_file="docker-compose.dev.yml"
readonly max_pull_attempts=4

# 以有限次数和指数退避拉取镜像，吸收 Docker Hub 的短暂网络抖动。
pull_images_with_retry() {
  local attempt
  local retry_delay

  for ((attempt = 1; attempt <= max_pull_attempts; attempt += 1)); do
    echo "拉取 E2E 依赖镜像（第 ${attempt}/${max_pull_attempts} 次）"
    if docker compose -f "${compose_file}" pull; then
      return 0
    fi

    if ((attempt == max_pull_attempts)); then
      echo "E2E 依赖镜像在 ${max_pull_attempts} 次尝试后仍拉取失败" >&2
      return 1
    fi

    retry_delay=$((5 * 2 ** (attempt - 1)))
    echo "镜像拉取失败，${retry_delay} 秒后重试" >&2
    sleep "${retry_delay}"
  done
}

# 启动已经拉取的镜像并等待健康检查完成，失败时输出容器诊断信息。
start_dependencies() {
  if docker compose -f "${compose_file}" up -d --pull never --wait --wait-timeout 90; then
    return 0
  fi

  docker compose -f "${compose_file}" ps --all || true
  docker compose -f "${compose_file}" logs --no-color || true
  return 1
}

pull_images_with_retry
start_dependencies
