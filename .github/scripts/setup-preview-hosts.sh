#!/usr/bin/env bash
# 文件功能：为 E2E 预览域配置 hosts 解析，使系统 DNS 与 Playwright 的 ApiRequestContext 也能访问 preview.localhost。

set -euo pipefail

# 与 backend/app/services/preview_origin_service.py 的回环改写保持一致；
# 两侧一致性由 tests/contracts/repository/deployment.test.ts 保护。
readonly preview_hostname="preview.localhost"
readonly preview_address="127.0.0.1"
readonly hosts_file="${PREVIEW_HOSTS_FILE:-/etc/hosts}"

# 以 hosts 文件本身为准，而不是只看 getent 结果：
# systemd-resolved 会按 RFC 6761 把 *.localhost 解析到回环，但可能优先返回 ::1，
# 而 Backend 与 Runtime 只监听 127.0.0.1；显式写入 IPv4 记录才能保证 Playwright 与 Node DNS 命中同一目标。
if grep -Eq "^[[:space:]]*${preview_address}[[:space:]]+${preview_hostname}([[:space:]]|$)" "${hosts_file}"; then
  echo "${hosts_file} 已包含 ${preview_address} ${preview_hostname}，跳过写入"
  exit 0
fi

echo "写入 hosts：${preview_address} ${preview_hostname} -> ${hosts_file}"
# GitHub Actions 的 ubuntu runner 使用免密 sudo；本项目 E2E 只在 Linux runner 上执行。
echo "${preview_address} ${preview_hostname}" | sudo tee -a "${hosts_file}" >/dev/null

# 写入未生效说明 hosts 不可写或路径不对，按失败处理，避免 E2E 中途才报 DNS 错误。
if ! grep -Eq "^[[:space:]]*${preview_address}[[:space:]]+${preview_hostname}([[:space:]]|$)" "${hosts_file}"; then
  echo "写入后 ${hosts_file} 仍缺少 ${preview_hostname}，请检查该文件是否可写" >&2
  exit 1
fi

echo "预览域 ${preview_hostname} 解析已就绪"
