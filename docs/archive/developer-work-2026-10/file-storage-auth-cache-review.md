# 代码审查报告：用户文件存储鉴权与缓存改造

- **审查基线**：`a94ae5703c99237eb9b9c5799722c7f54310f4d2`（下称 `a94ae57`）
- **审查范围**：`a94ae57..HEAD`（19 个提交，`ddd0c35` → `fc9d907`）**加**当时工作区未提交改动
- **基准文档**：`docs/developer/runtime-integration/file-storage-auth-cache-plan.md`（W01–W12）
- **验证方式**：静态审查 + 新增单测复核，未做端到端部署验证

## 1. 变更规模

| 维度 | 数量 |
| --- | --- |
| 已提交 | 19 提交 / 59 文件 / +4967 −363 |
| 未提交工作区 | 63 文件 / +552 −514 |
| 新增未跟踪文件 | 7 |

核心新增/重写模块：

- `backend/app/services/file_auth_service.py`（+586）
- `backend/app/services/protected_file_response.py`（新增）
- `backend/app/api/business_origin.py`（新增）
- `backend/app/services/preview_origin_service.py`（新增）
- `backend/app/services/screenshot_artifact_service.py`（新增）
- `backend/tests/unit/test_private_delivery_regressions.py`（新增）

## 2. 验证结果

```
backend/tests/unit -q  →  726 passed, 1 warning in 52.55s
```

唯一 warning 为 httpx 的 `cookies=<...>` 每请求传参弃用提示（`test_public_surfaces_closed.py::test_build_artifacts_protected_access_flow`），与本次安全语义无关，属存量测试写法问题。

受保护文件链路相关的 11 个测试文件全部通过；单独重跑 `test_file_auth_core.py`、`test_object_cache_concurrency.py`、`test_private_delivery_regressions.py`、`test_private_asset_chains.py` 得 `22 passed`。

## 3. 总体结论

**无高危问题。** 改造方向正确且执行到位：匿名访问面已在 nginx 与路由两侧双重收口，票据体系的作用域绑定（artifact / job / attempt / lease）没有发现可绕过的路径，缓存并发与流式生命周期的处理比改造前明显更严谨，旧公开 URL 形态已在前端与构建产物中清理干净。

发现 **3 项中危、4 项低危、2 项建议**，均集中在**前端续签链路的覆盖完整性与交互时序**，以及**少量遗留字段/启发式判断**。后端鉴权与缓存核心未发现正确性或安全性缺陷。

---

## 4. 中危问题

### M1｜组件预览与可视化编辑预览完全未接入续签

**位置**
- `editor/src/composables/useComponentPreviewSession.ts:66-73`
- `editor/src/components/component-preview/ComponentPreviewWorkbench.vue:133-139`
- `editor/src/components/page-detail/visual-edit/PageVisualEditPanel.vue:112-118`
- 对照：`editor/src/composables/useRuntimePreviewRecovery.ts:37`

**问题**
`useRuntimePreviewRecovery` 的自动续签有两个硬前置：

```ts
// useRuntimePreviewRecovery.ts:37
if (!options.artifactId || !options.onRenewed) return
```

而 `useComponentPreviewSession` 构造该 hook 时**未传 `artifactId` 与 `onRenewed`**：

```ts
const recovery = useRuntimePreviewRecovery({
  frameUrl: () => previewUrl.value,
  sourceKey: () => null,
  isPending: () => previewStatus.value === 'generating',
  enabled: () => previewLoader !== null,
  recover: async () => { ... },
  onFailure: error => markPreviewError(...),
  // 缺 artifactId / onRenewed → scheduleAutoRenew 首行即 return
})
```

因此组件预览既没有到期前排期续签，也没有 `visibilitychange` 兜底续签，只剩「Runtime 主动回传错误码 → 全量重建」这一条路径。

可视化编辑更彻底：`PageVisualEditPanel.vue` 用的是裸 iframe，直接绑定 `session.artifact.value.preview_url`，连 `RuntimePreviewFrame` 的恢复 hook 都没有。

**影响**
票据 TTL 在 `PreviewService.create_preview_artifact` 中**硬编码为 300 秒**：

```python
# backend/app/services/preview_service.py:111
token_ttl_seconds = 300
```

而 artifact 本体 TTL 由 `settings.runtime_preview_artifact_ttl_seconds` 决定（存于 manifest `artifact_expires_at`），通常远大于 300 秒。也就是说组件预览 / 可视化编辑在打开 **5 分钟**后票据必然过期，此时：

- 组件预览：iframe 顶部文档 `/preview/artifacts/{id}?token=` 直接返回 401，宿主页根本没加载，**不会**触发 `COMPONENT_PREVIEW_ERROR_EVENT`，`tryRecover` 没有入口，界面停留在失效 iframe；
- 可视化编辑：同样失效，且没有任何错误通道。

用户表现为「编辑着突然白屏/报错，只能刷新页面」。这是本次改造引入的**功能回退**——改造前该路径为匿名代理，不存在 TTL 概念。

**修复建议**
1. `useComponentPreviewSession` 补传 `artifactId: () => previewArtifactId.value` 与 `onRenewed`（写回 `previewUrl` 并 `refreshPreviewFrame()`）；
2. 可视化编辑补传 artifactId，或直接改用 `RuntimePreviewFrame`（它已内置续签与重试 UI）；
3. `tryRecover` 之外增加 `load` / `error` 事件兜底：iframe 的顶层 401 无法经 postMessage 上报，可以在宿主侧用 `onerror` 或对 `preview_url` 做一次探活来补这个缺口；
4. 建议把 `token_ttl_seconds = 300` 提为配置项，与 `runtime_preview_artifact_ttl_seconds` 一起收口，避免「硬编码 5 分钟」的隐含约束散落在调用方。

---

### M2｜续签失败不区分错误类型，一律降级为全量重建并消耗恢复预算

**位置**：`editor/src/composables/useRuntimePreviewRecovery.ts:62-70`

```ts
} catch {
  // 续签失败（如 artifact 已 410 过期或无权限），回退至全量重建
} finally { ... }
if (currentSequence === sequence && options.enabled?.() !== false && !options.isPending?.()) {
  tryRecover('PREVIEW_CONTEXT_INVALID')
}
```

**问题**
`catch {}` 丢弃了错误对象，所有续签失败——**网络抖动、502、超时、前端离线、后端重启**——都被当成「artifact 已失效」，直接走全量重建。

而 `tryRecover` 会立刻把 `attempted` 置为 `true`（第 77 行），即**消耗掉本轮唯一的重建预算**。恢复预算只在 `reset()` 时重置，`reset()` 由 ready 消息、用户显式重试、`sourceKey` / `artifactId` 变化触发。

**影响**
一次瞬时网络故障 → 续签失败 → 全量重建（重跑 artifact 创建 + 模块编译，成本和耗时远高于续签）→ 若重建期间网络仍未恢复 → 重建也失败 → `attempted === true`，**自动恢复链彻底锁死**，用户只能手动点「重新生成预览」。原本 200ms 的续签请求变成了数十秒的重建 + 一次不可逆的预算消耗。

**修复建议**
1. `catch (error)` 读取结构化错误码，只对 `PREVIEW_ARTIFACT_EXPIRED`（410）、`FILE_ACCESS_REQUIRED/INVALID`（401/403）、`ARTIFACT_NOT_FOUND`（404）降级重建；
2. 网络类错误（`TypeError`、超时、5xx）应记为一次**可重试的续签失败**，按退避重排 `scheduleAutoRenew`，**不动 `attempted`**；
3. 可考虑给续签单独设小重试预算（例如 2 次），与重建预算解耦。

---

### M3｜`window.open` 被移到 `await` 之后，私有构建入口可能被弹窗拦截

**位置**：`editor/src/views/PagesView.vue:1370-1383`

```ts
async function handleBuildArtifactOpen(job: ProjectBuildJob): Promise<void> {
  if (!canOpenProjectBuildArtifact(job) || !projectDetails.value) return
  try {
    const access = await getProjectBuildJobAccess(projectDetails.value.id, job.id)  // ← await
    if (access.browse_url) {
      window.open(access.browse_url, '_blank', 'noopener,noreferrer')              // ← 已在 await 之后
    }
  } catch (error) { ... }
}
```

**问题**
现代浏览器要求 `window.open` 处于**瞬时用户激活**（transient user activation，通常约 5 秒且会被异步边界之外的调度进一步削弱）窗口内。把 `window.open` 放在 `await` 之后，激活状态很可能已经失效，尤其是：

- 后端 `/build-jobs/{id}/access` 需要签发令牌，耗时不稳定（冷启动、DB 抖动）；
- 某些浏览器/扩展对 `await` 之后的弹窗判定更严格。

**影响**
点击「打开构建产物」后**没有任何反应**（弹窗被静默拦截），控制台可能仅有一条被抑制的提示。这是本次改造新引入的回归——改造前 URL 已知，可以同步 `window.open`。

**修复建议**（任选其一，推荐 1）
1. 先同步开启占位窗口并保住引用，拿到 URL 后再赋值：
   ```ts
   const tab = window.open('', '_blank', 'noopener,noreferrer')
   const access = await getProjectBuildJobAccess(...)
   if (tab) tab.location.href = access.browse_url
   ```
   （注意 `noopener` 会让 `tab` 为 `null`，需要改用 `tab.opener = null` 的等价写法。）
2. 改为「先预取 access、缓存 browse_url，点击时同步打开」；
3. 退化为同页导航 / 下载，规避弹窗策略。

---

## 5. 低危问题

### L1｜构建产物入口开关仍绑定待废弃的公开字段

**位置**：`editor/src/utils/project-build.ts:119-121`

```ts
export function canOpenProjectBuildArtifact(job: ProjectBuildJob): boolean {
  return Boolean(job.artifact_proxy_url)
}
```

`artifact_proxy_url` 是后端 `ProjectBuildJob` 计算属性（`backend/app/models/project_build_job.py:45-52`）暴露的**遗留公开字段**，返回 `{backend_public_base_url}/build-artifacts/{project}/{job}/`——一个不带票据、按新策略必然 404 的 URL。规划中该字段被列为待废弃。

**影响**：字段一旦移除，`canOpenProjectBuildArtifact` 恒为 `false`，入口按钮会**静默消失**，且不会有测试失败。属面向未来的耦合风险，当前功能正常。

**修复建议**：改为基于真实语义判断，例如 `Boolean(job.artifact_storage_key)` 或后端新语义字段；同时把 `artifact_proxy_url` 标注 `@deprecated` 并加迁移测试。

### L2｜Runtime 素材路径仍依赖字符串拼接 + 子串启发式

**位置**：`runtime/src/core/utils/path.ts:274-288`

```ts
const rawUrl = joinUrlPath(assetBaseUrl, params.mappedAssetPath)
if (previewToken && (...) && (rawUrl.includes('/preview/artifacts/') || rawUrl.includes('/assets/')) && !rawUrl.includes('token=')) {
  const separator = rawUrl.includes('?') ? '&' : '?'
  return `${rawUrl}${separator}token=${encodeURIComponent(previewToken)}`
}
```

**影响**
- `includes('/assets/')` 是全串子串匹配，manifest 中任何含该片段的普通资源路径都会被拼上预览令牌；
- 与本次改造确立的「结构化访问描述」（manifest 显式声明资源来源与是否需要身份）方向不一致，是残留的启发式；
- 目前未发现可被外部输入利用的路径（`mappedAssetPath` 受 manifest 白名单约束），故定级低危。

**修复建议**：把「是否需要附带票据」下沉为 manifest 的显式字段（如 `asset_base_url_auth: none | preview_token | service_token`），`path.ts` 只做查表，不再做子串推断。

### L3｜素材下载失败的错误消息会把带令牌的原始 URL 写进文本

**位置**：`runtime/src/core/plugins/runtime-build-runner.ts:692-693, 864-877, 904-912`

```ts
} catch (error) {
  throw buildAssetFetchNetworkError(assetUrl, error, context)   // ← 传入的是改写前的原始 assetUrl
}
```

```ts
// appendAssetFetchContext
assetUrl ? `URL ${assetUrl}` : '',    // ← 原样内联，不脱敏
```

而 `path.ts:276-285` 确实会给素材 URL 追加 `?token=<预览 JWT>`；`runtime-private-assets.test.ts:41` 也把 `` `${base}/hash1?token=P` `` 作为 `fetchAssetBinary` 的合法入参。**成功路径没问题**（请求 URL 已被改写为内部地址且不带令牌，测试有断言），但**网络异常路径**会把原始带令牌 URL 原样写进 `BUILD_ASSET_FETCH_FAILED` 的 message，进而出现在构建任务错误、日志与编辑器 UI 中。

仓库内已有脱敏约定（`S3PerformanceAndDiagnostics.sanitizeUrl` 会把 `token=` 替换为 `[REDACTED]`，`client-logger` 亦有 `runtime failed?token=secret` 的脱敏用例），此路径绕过了该约定。

**修复建议**：`buildAssetFetchNetworkError` 改为接收已改写的 `internalAssetUrl`（或对入参 URL 先做 query 脱敏再内联）。这是一行改动。

### L4｜未监听 `@renew` 的宿主在续签后状态不一致

**位置**：`editor/src/components/runtime-preview/RuntimePreviewFrame.vue:96-117`

续签成功后 URL 只写在组件内部的 `renewedFrameUrl`，并通过 `emit('renew', newUrl)` 对外通告。已正确接线的宿主：`PageDetailPreviewPanel.vue:44,69` → `PageDetailView.vue:117`。

**未接线**（开启了 `auto-recover` 并传了 `artifact-id`，但没写 `@renew`）：

- `editor/src/components/project/AssetPreviewFrame.vue:19-25`
- `editor/src/components/page-detail/PageVersionHistoryDialog.vue:90-93`
- `editor/src/components/component-preview/ComponentVersionHistoryDialog.vue:96-99`

**影响**：iframe 本身能正常续签（`effectiveFrameUrl` 生效），但父组件持有的 `frameUrl` prop 仍是旧票。一旦父组件因任何原因重算该 prop，`watch(() => props.frameUrl, ...)`（第 113-117 行）会**清空 `renewedFrameUrl`**，iframe 立刻退回旧票据并失效。属状态双写不一致，日常路径下不触发。

**修复建议**：这三个宿主补 `@renew` 写回自身 state；或由 `RuntimePreviewFrame` 用 `v-model:frame-url` 统一接管，避免双写。

---

## 6. 建议项

### S1｜`referrerpolicy="same-origin"` 与规划的 `no-referrer` 不一致

`editor/src/components/runtime-preview/RuntimePreviewFrame.vue:10` 与 `editor/src/components/component-preview/ComponentPreviewWorkbench.vue:138` 均使用 `same-origin`，规划文档要求 `no-referrer`；Runtime 侧 HTML 响应头已正确设置 `Referrer-Policy: no-referrer`（`runtime-saas-preview.ts:1452`）。

当前风险很低（`same-origin` 下跨源 iframe 不发 Referer，同源仅暴露编辑器自身路由），但**双策略并存**增加了后续推理成本。建议按规划统一为 `no-referrer`（iframe 属性优先于文档头，不会削弱 Runtime 自身的头设置）。

### S2｜登出时未清理预览资源引用

`editor/src/stores/auth.ts` 的 `signOut` 未显式清理预览 artifact 引用（`previewArtifactId` / `previewUrl` / 定时器）。多账号切换场景下，残留状态可能让下一个会话短暂复用上一个会话的票据 URL。建议在 `signOut` 中统一清理预览上下文并 `clearRenewTimer`。

---

## 7. 已确认无问题（重点复核项）

下列各项经代码与测试双向核对，**未发现问题**：

- **匿名面收口**：nginx `web-presentation.conf` 中 `/public`、`/public/`、`/media` 均为 404；`/build-artifacts/` 由 404 改为 proxy 到 backend 后，鉴权在 Backend 缓存/正文返回之前完成，目录级阻断不会误放行。
- **票据作用域绑定**：Runtime 服务令牌强制绑定 `artifact_id`（空值直接 500 `RUNTIME_SERVICE_TOKEN_ARTIFACT_REQUIRED`）；构建令牌绑定 `job_id` / `attempt_id` / `lease_owner`；未发现跨 artifact 复用的可行路径。
- **过期令牌**：`verify_signed_token` 增加 `"require": ["exp"]`，无 `exp` 的令牌被拒绝；续签不会静默延长 artifact 本体寿命（以 manifest `artifact_expires_at` 为准，过期抛 410）。
- **源站隔离**：`isolated_preview_base_url()` 对远程同主机名直接 503 `PREVIEW_ORIGIN_NOT_ISOLATED`；宿主页 CSP 为 `default-src 'none'` + nonce；双向 message 桥严格校验 `event.source` 与 `event.origin`。
- **CSRF**：`enforce_business_origin` 对 `/api/` 非安全方法校验 Origin/Referer，且 `supplied is None` 配合 `sec-fetch-site ∈ {cross-site, same-site}` 也拒绝；测试覆盖 `https://preview.example` 与 `null` 源站均 403。
- **对象缓存并发**：并发回源合并（`_in_flight_downloads` + `asyncio.shield`）、原子提升（tmp + `os.replace`）、读占用计数（`_read_pins`）保护在途响应。`test_cache_sweep_keeps_active_stream` 验证「容量清零后 sweep 仍不删已交给响应的文件」，且事后 `_read_pins` 归零。
- **流式生命周期**：`ScopedFileResponse` 把 `AsyncExitStack.aclose()` 放进 ASGI `__call__` 的 `finally`，客户端取消/断连时也能释放读占用；条件请求分支在提前返回时立即释放。
- **内容寻址截图**：新 key `page-screenshots/{page_id}/objects/{sha256}.png`；旧可变 key 走 `read_object` + 实际字节 ETag，**不进入**不可变缓存，避免同 key 内容漂移。
- **构建 Worker**：`fetchAssetBinary` 把 `/preview/artifacts/` 改写为 `/internal/runtime/preview-artifacts/`，正则严格限定 `.../assets/{hash}`，`redirect: 'error'` 防跟随重定向泄露身份；无 public fallback。共享凭证用 `hmac.compare_digest` 常量时间比较，未配置时 fail-closed 503。
- **snapDOM 导出**：先做 manifest 白名单校验再读缓存；仅允许「同一资源身份 + 允许的查询变体」，额外查询参数或其他 artifact 一律拒绝。
- **构建产物隔离**：业务源站收到有效票据后 307 跳转到 `isolated_preview_origin()`；`browse_url` 亦改由 `isolated_preview_origin()` 生成，不再用 `backend_public_base_url`。
- **前端**：无旧公开 URL 拼接残留；未发现把 token 拼进 base URL 再追加 hash 的写法；日志脱敏路径完整。

---

## 8. 修复优先级建议

| 优先级 | 项 | 理由 |
| --- | --- | --- |
| P0 | M1 | 已上线的功能回退，5 分钟必现 |
| P0 | M3 | 用户可感知的交互失灵，改动量极小 |
| P1 | M2 | 显著放大故障半径，易误判为"服务不可用" |
| P1 | L3 | 一行改动即可消除令牌外泄面 |
| P2 | L1 / L4 | 面向未来的耦合与状态一致性 |
| P2 | L2 / S1 / S2 | 技术债与一致性收敛 |

---

## 9. 审查局限

- 未做端到端部署验证（nginx 实际生效行为、跨主机名 iframe 的真实 Referrer/Origin 表现）；
- 未覆盖未提交改动之外的运行时配置差异（如 `runtime_preview_artifact_ttl_seconds` 在生产环境的取值）；
- 前端问题基于静态阅读与现有单测推断，未在浏览器中复现 M1 / M3。

---

## 10. 整改与闭环落地记录（2026-10-16）

本章记录**第一轮**审查发现的整改落地情况（M1–M3、L1–L4、S1 与安全补丁）；S2 的整改与第二轮独立复核（P0–P2）的处理见 §11。

| 项 | 描述 | 整改实施与提交 | 状态 |
| :--- | :--- | :--- | :--- |
| **M1** | 组件预览、可视化编辑、全屏弹窗续签 | 1. `useComponentPreviewSession` 补齐 `artifactId`、`onRenewed` 闭环并由 `ready` 消息重置恢复预算；<br>2. `usePageVisualEditSession` 内置 `useRuntimePreviewRecovery` 自动续签机制；<br>3. `PageDetailPreviewPanel` 全屏预览弹窗增加 `auto-recover` 属性并绑定 `activePreviewFrameUrl`；<br>4. 后端 `Settings` 增加 `runtime_preview_token_ttl_seconds = 300` 配置项，消除硬编码约束。<br>提交：`0a04ea6`（后端）、`c5f4892`（前端） | **已闭环** |
| **M2** | 续签失败区分网络抖动与终态失效 | `useRuntimePreviewRecovery` 在捕获续签异常时，精准识别 410/401/403/404 终态并才降级全量重建；对网络抖动与临时 5xx 按 10 秒退避重试，不消耗 `attempted` 全量重建预算。<br>提交：`8e8a9ae` | **已闭环** |
| **M3** | 构建产物打开异步弹窗拦截 | `PagesView.vue` 的 `handleBuildArtifactOpen` 改为在用户点击同步手势内预先打开 `about:blank` 标签页，拿到短期签名 `browse_url` 后再跳转并切断 opener，并在授权失败时自动关闭占位页。<br>提交：`8e8a9ae` | **已闭环** |
| **L1** | 构建产物入口判断解耦废弃字段 | `project-build.ts` 的 `canOpenProjectBuildArtifact` 改为优先基于 `job.artifact_storage_key` 判定，兼容保留 `artifact_proxy_url`。<br>提交：`8e8a9ae` | **已闭环** |
| **L2** | Runtime 素材路径启发式收敛 | 第一轮以 `isProtectedPreviewAssetUrl` 收窄匹配范围；第二轮改为由 Backend 显式签发 `asset_base_url_auth` 声明、运行时查表（见 §11），启发式仅保留在旧票据的兼容推断中。<br>提交：`e9e3dfa`、第二轮整改 | **已闭环**（最终形态见 §11） |
| **L3** | 构建素材网络异常日志 URL 脱敏 | `runtime-build-runner.ts` 引入 `sanitizeAssetUrl` 对下载失败的静态资源 URL 执行正则凭据脱敏，消除构建错误与控制台的 Token 外泄面。<br>提交：`e9e3dfa` | **已闭环** |
| **L4** | 宿主组件监听 `@renew` 保持状态一致 | `AssetPreviewFrame.vue`、`PageVersionHistoryDialog.vue`、`PageDetailView.vue`、`ComponentVersionHistoryDialog.vue`、`WorkspaceComponentWorkbench.vue` 统一接入 `@renew` / `@renew-preview` 并写回上层状态。<br>提交：`c5f4892` | **已闭环** |
| **S1** | iframe 统一 `referrerpolicy="no-referrer"` | `RuntimePreviewFrame.vue`、`ComponentPreviewWorkbench.vue`、`PageVisualEditPanel.vue` 全部统一为 `referrerpolicy="no-referrer"`。<br>提交：`8e8a9ae`、`c5f4892` | **已闭环** |
| **安全补丁** | 审查遗留的安全保留字段与越权漏洞 | 补丁 `146aa31` 已入库：Token 保留声明强制覆盖、External API 跨工作空间隔离校验、内部回源 410 过期识别、服务令牌最小下限保护。<br>提交：`146aa31` | **已闭环**（其中"服务令牌最小 60 秒下限"与规划 §4.2 冲突，第二轮已改为不超过来源 P 剩余期限，见 §11） |
| **S2** | 登出时未清理预览资源引用 | 第一轮未整改（记录于本节时缺项），第二轮补齐：`useRuntimePreviewRecovery` 增加会话级取消注册表，登出与 401 失效统一清理续签计时器。见 §11。 | **已闭环** |

---

## 11. 第二轮独立复核与整改记录（2026-10-16，P0–P2）

- **复核范围**：`a94ae57..HEAD` 共 25 个提交（含第一轮整改后新增的 6 个提交）
- **复核方式**：代码走查 + 全量门禁实跑。第一轮只跑了 `backend/tests/unit`，`-m api` 与 `-m integration` 未覆盖，这是本轮发现阻断项的直接原因
- **结论**：改造主线（票据作用域、缓存并发、公开面收口、源站隔离）未发现新增高危；本轮问题集中在**门禁一致性、旧用例迁移、期限语义与启发式残留**

### 11.1 复核发现

| 级别 | 问题 | 证据（修复前） |
| :--- | :--- | :--- |
| P0 | `enforce_business_origin` 与 PAT 控制台端点级 CSRF 各自维护来源白名单：中间件只认 `BACKEND_PUBLIC_BASE_URL` ∪ CORS，端点级还额外信任请求自身 Host | `-m api` 5 项失败（`tests/api/test_access_tokens.py`）；`test:backend:api` 是每次质量门禁都执行的步骤。部署侧同源影响：`localhost` 与 `127.0.0.1` 访问差异会让写接口（含登录）全部 403 |
| P0 | 公开面关闭后旧正向用例未迁移 | `-m integration` 10 项失败：`test_public_assets.py`×5、`test_public_cached_assets.py`×3 仍断言已关闭的 `/public/*` 返回 200/302；`test_project_build.py`×2 仍断言匿名 `/build-artifacts` 返回 200 与 `BUILD_ARTIFACT_NOT_FOUND` |
| P1 | 服务令牌 TTL 使用 `max(60, exp-now)` 最小下限 | 与规划 §4.2「不得通过最小 TTL 把授权延长到来源到期以后」冲突，S 令牌最多比来源 P 多活 55 秒 |
| P1 | 整改记录声称「所有问题均已闭环」，但 S2 未整改也未列入闭环表 | `stores/auth.ts` 的 `signOut` 未清理预览续签计时器 |
| P2 | 续签终态判定对错误消息做数字子串匹配（`includes('410')` 等） | `timeout of 10410ms exceeded` 一类文案会被误判终态，触发全量重建并消耗恢复预算 |
| P2 | Runtime 素材票据仍靠路径子串启发式判定 | 与规划「结构化访问描述」方向不一致 |
| P2 | `renew_preview_access` 在快照缺少归属信息时不校验任何权限即签发票据 | 无授权依据的签发路径，应为 fail-closed |

### 11.2 整改内容

| 项 | 整改 |
| :--- | :--- |
| P0-1 | 新增 `app/api/business_origin.py::trusted_business_origins()` 作为唯一受信来源白名单（业务公开基址 ∪ CORS，统一小写比较），全局中间件与 PAT 控制台端点级校验共用；端点级不再信任请求自身 Host；403 文案给出受信来源提示。测试改用平台公开基址作为 Origin，并新增白名单一致性守卫测试；Lite 模板与文档把 `http://localhost:8080` 一并加入默认 `CORS_ORIGINS` |
| P0-2 | 删除 `test_public_assets.py`、`test_public_cached_assets.py`，新增 `test_workspace_asset_delivery.py`（登录要求、本地交付、S3 回源与缓存复用、字体私有桶、版本校验、对象缺失共 5 项，含本地对象根目录隔离夹具）；`test_project_build.py` 两项改走私有构建授权接口（匿名 404、票据浏览、跨项目与删除后语义）；顺带修复 `test_preview_version_binding.py` 比较全量 claims 导致的跨秒偶发失败 |
| P1-3 | 服务令牌 TTL 收敛为 `TokenService.resolve_preview_service_token_ttl()`（不超过来源 P 剩余期限，`max(1, exp-now)`），预览服务与截图服务两处调用点统一，并新增「不得延长」回归用例 |
| P1-4 | `useRuntimePreviewRecovery` 增加会话级续签取消注册表，`clearAllPreviewRenewTimers()` 在登出与 401 失效时统一清理；新增登出清理回归用例（含未清理时会触发续签的正例对照） |
| P2-5 | 终态判定只认结构化状态码与错误码文本，不再对消息里的数字做子串猜测；新增超时文案不被误判的用例 |
| P2-6 | 素材票据类型下沉为显式声明：新增 `app/services/asset_access_policy.py::resolve_asset_base_url_auth()`，签发预览上下文时写入 `asset_base_url_auth`；Runtime 契约新增 `PreviewAssetBaseAuth` 与 `resolvePreviewAssetBaseAuth()`（旧票据缺失声明时按签发基础地址退化推断），`path.ts` 改为查表并删除启发式 |
| P2-8 | `renew_preview_access` 在归属信息缺失或非法时 fail-closed（404），补齐 artifact 到期时间解析异常兜底 |

### 11.3 本轮验证结果（HEAD 工作区）

| 门禁 | 结果 |
| :--- | :--- |
| `pytest -m unit` | **742 passed**（含新增票据声明、白名单一致性、登出清理与 fail-closed 用例） |
| `pytest -m api` | **219 passed**（此前 5 项失败已修复） |
| `pytest -m integration` | **325 passed / 7 skipped / 0 failed**（332 项；此前 10 项失败已迁移或重写） |
| `test:contracts:generated` | **通过**（258 paths / 340 schemas；服务令牌交换端点描述变更已重新生成，`api.generated.ts` 无变化） |
| Editor | `vue-tsc -b` 通过；vitest **812 passed**（145 文件）；生产构建通过 |
| Runtime | `vue-tsc -b` 通过；vitest **869 passed / 3 skipped**（120 文件）；生产构建通过 |
| 网关契约（真实 Nginx） | 通过（本轮未改动网关路由） |

补充说明：

- 两个平台相关测试的偶发问题已一并处理：`test_preview_version_binding.py` 的全量 claims 比较改为忽略 `iat/exp/jti`；`runtime-build-worker.test.ts` 的超时恢复用例把 200ms 预算放宽到 1500ms（首次调用永久不响应，超时必触发；200ms 在 Windows 冷启动下会误报，属测试预算问题而非 worker 逻辑缺陷）。
- 本机验证时，沙箱的批量删除守卫会拦截 `vite build` 清空 `dist/` 与 pytest 清理临时目录，表现为构建/汇总行被中断；生产构建已用 `--emptyOutDir=false` 单独复验通过，上述中断不代表代码问题。
- 仍未完成的是需要真实环境的事项：生产桶策略与 ACL、真实 S3 兼容服务、多副本、预览域 DNS/TLS 与 host-only Cookie 实机验收、一个计费周期的成本观测（与规划 §12/§13 一致）。
