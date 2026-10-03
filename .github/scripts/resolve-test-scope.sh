#!/usr/bin/env bash
# 文件功能：按事件类型与 git diff 结果分级决定 platform-test 的门禁范围，输出 full_tests、run_runtime、e2e_scope 与镜像 smoke 矩阵。
#
# 分级原则：
# - schedule / workflow_dispatch 是全量入口，不依赖 diff；
# - PR 与 main push 依据变更文件收敛，纯文档改动不触发 integration、E2E 与镜像构建；
# - 镜像 smoke 只重建内容真正受影响的变体（平台/lite 由 Backend+Editor 决定，lite 另含 Runtime 源码）；
# - 拿不到 diff base 时保守升级为全量，绝不静默降级。

set -uo pipefail

write_output() {
  # 写入 GitHub Actions step output。
  echo "$1=$2" >> "${GITHUB_OUTPUT}"
}

readonly FULL_MATRIX='[{"name":"full","file":"deploy/docker/Dockerfile.platform","tag":"web-presentation:ci-smoke","cache_scope":"platform"},{"name":"lite","file":"deploy/docker/Dockerfile.lite","tag":"web-presentation:sqlite-lite-ci-smoke","cache_scope":"platform-lite"},{"name":"runtime","file":"runtime/Dockerfile","tag":"web-runtime-vue:ci-smoke","cache_scope":"runtime"},{"name":"renderer","file":"renderer/Dockerfile","tag":"web-presentation-renderer:ci-smoke","cache_scope":"renderer"}]'

# 纯文档与仓库元数据改动：不进全量门禁。
docs_only_re='^(docs/|(README|AGENTS|DESIGN|LICENSE)\.md$|\.gitignore$|\.gitattributes$)'
# 会被打进平台镜像的构建输入，与 deploy/docker/Dockerfile.platform 的 COPY 清单对齐。
platform_re='^(deploy/|backend/|editor/|scripts/|Dockerfile|\.dockerignore$|package\.json$|pnpm-lock\.yaml$|pnpm-workspace\.yaml$|uv\.lock$|runtime/package\.json$|runtime/src/runtime-kit/manifest/|\.github/)'
# Runtime 镜像与 Runtime 门禁的输入。
runtime_re='^(runtime/|pnpm-lock\.yaml$|pnpm-workspace\.yaml$|package\.json$|\.github/)'
# Renderer 镜像的输入。
renderer_re='^(renderer/|packages/|uv\.lock$|\.github/)'

emit_full_scope() {
  # 输出全量门禁范围，供定时、手动和 base 缺失时使用。
  local scope
  scope="${1:-smoke}"
  write_output full_tests true
  write_output run_runtime true
  write_output e2e_scope "${scope}"
  write_output image_matrix "${FULL_MATRIX}"
}

if [[ "${EVENT_NAME}" == "schedule" ]]; then
  emit_full_scope all
  exit 0
fi

if [[ "${EVENT_NAME}" == "workflow_dispatch" ]]; then
  if [[ "${INPUT_FULL_TESTS}" == "true" ]]; then
    emit_full_scope all
  else
    write_output full_tests false
    write_output run_runtime false
    write_output e2e_scope smoke
    write_output image_matrix '[]'
  fi
  exit 0
fi

# 解析 diff base：PR 用目标分支，push 用事件携带的 before SHA。
base_ref=""
if [[ "${EVENT_NAME}" == "pull_request" ]]; then
  candidate="origin/${BASE_REF:-main}"
  if git rev-parse --verify --quiet "${candidate}" >/dev/null; then
    base_ref="${candidate}"
  fi
elif [[ -n "${BEFORE_SHA}" ]] && git cat-file -e "${BEFORE_SHA}^{commit}" 2>/dev/null; then
  base_ref="${BEFORE_SHA}"
fi

if [[ -z "${base_ref}" ]]; then
  echo "未能解析 ${EVENT_NAME} 的 diff base，保守升级为全量门禁。" >&2
  emit_full_scope smoke
  exit 0
fi

if [[ "${EVENT_NAME}" == "pull_request" ]]; then
  changed_files="$(git diff --name-only "${base_ref}...${HEAD_SHA}")"
else
  changed_files="$(git diff --name-only "${base_ref}" "${HEAD_SHA}")"
fi

echo "diff base：${base_ref}"
echo "变更文件："
echo "${changed_files}"

full_tests=false
run_runtime=false
platform_hit=false
runtime_hit=false
renderer_hit=false

while IFS= read -r path; do
  [[ -z "${path}" ]] && continue
  [[ "${path}" =~ ${docs_only_re} ]] && continue

  # 任何非文档改动都进入全量门禁；文档改动只跑快速门禁。
  full_tests=true

  [[ "${path}" =~ ${platform_re} ]] && platform_hit=true
  [[ "${path}" =~ ${runtime_re} ]] && runtime_hit=true
  [[ "${path}" =~ ${renderer_re} ]] && renderer_hit=true
done <<< "${changed_files}"

legs=()
if [[ "${platform_hit}" == true ]]; then
  legs+=('{"name":"full","file":"deploy/docker/Dockerfile.platform","tag":"web-presentation:ci-smoke","cache_scope":"platform"}')
  # lite 镜像内置 Runtime 源码，Runtime 变更同样需要复查 lite。
  legs+=('{"name":"lite","file":"deploy/docker/Dockerfile.lite","tag":"web-presentation:sqlite-lite-ci-smoke","cache_scope":"platform-lite"}')
fi
if [[ "${runtime_hit}" == true ]]; then
  legs+=('{"name":"runtime","file":"runtime/Dockerfile","tag":"web-runtime-vue:ci-smoke","cache_scope":"runtime"}')
  if [[ "${platform_hit}" != true ]]; then
    legs+=('{"name":"lite","file":"deploy/docker/Dockerfile.lite","tag":"web-presentation:sqlite-lite-ci-smoke","cache_scope":"platform-lite"}')
  fi
fi
[[ "${renderer_hit}" == true ]] && legs+=('{"name":"renderer","file":"renderer/Dockerfile","tag":"web-presentation-renderer:ci-smoke","cache_scope":"renderer"}')

image_matrix='[]'
if [[ "${#legs[@]}" -gt 0 ]]; then
  image_matrix="[$(IFS=,; echo "${legs[*]}")]"
fi

write_output full_tests "${full_tests}"
# Runtime 门禁在全量范围内始终执行，与既有 E2E 前置保持一致。
if [[ "${full_tests}" == true || "${runtime_hit}" == true ]]; then
  run_runtime=true
fi
# 全量范围（E2E all）只由定时与手动入口承担，PR 与 main push 用 smoke。
write_output run_runtime "${run_runtime}"
write_output e2e_scope smoke
write_output image_matrix "${image_matrix}"

echo "分级结果：full_tests=${full_tests} run_runtime=${run_runtime} image_matrix=${image_matrix}"
