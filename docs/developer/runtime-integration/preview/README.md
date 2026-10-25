# 预览源站与 artifact 接入

本文记录当前 Backend、Runtime、Editor 和 Renderer 共用的预览入口。历史代理方案保存在[预览旧设计归档](../../../archive/developer-work-2026-10/preview-legacy/runtime-architecture.md)，不能作为当前实现依据。

## 入口与身份

1. Editor 通过 Backend 创建短期 preview artifact；Backend 在创建时校验用户和工作空间权限，并签发绑定 artifact 的短期预览票据 P。
2. 浏览器打开 Backend 的 `/preview/artifacts/{artifact_id}?token=...`。该入口验签、核对 artifact 并绑定 Runtime 构建版本，返回可信桥接宿主页；用户页面 HTML 在 `RUNTIME_PUBLIC_BASE_URL` 指定的**独立主机名**内执行。
3. Runtime 的 `/__preview` 消费已绑定版本的 P。Renderer 浏览器也使用本次 attempt 的 P；受控初始文档请求可使用预览请求头。Runtime 和构建 Worker 回源 Backend 内部接口时使用服务票据 S。P 与 S 不得混用。
4. 浏览器读取预览素材使用 artifact 范围的 P。Backend 在处理缓存、`304`、`HEAD`、`Range` 之前校验身份、artifact、资源版本；用户业务 Cookie 保持 host-only，预览域不得加入业务 CORS。

预览票据是短期持有式授权，不能描述为“只有原登录用户可访问”。Editor 的续签重新检查当前权限；artifact 过期或运行态清空后需要创建新预览，不能把旧 artifact 指向新内容。

## artifact 与运行时

- preview artifact 固化入口、配置、模块与资源映射，临时保存在运行态存储；具体数据与失效语义见[Backend 预览 artifact](../../backend/preview-artifacts.md)。
- 页面、工作空间组件和 previewSchema 的 import 边界以 [Runtime Kit 契约](../runtime-kit-contract.md)与 Backend 校验为准。
- Runtime 以内部服务身份读取 manifest、配置和模块，浏览器加载编译后的页面；构建使用独立的 build snapshot，不复用预览票据。
- Editor 与可信宿主页、Runtime 的消息须核对窗口、精确 origin、协议版本和 artifact。预览版本与错误处理见[预览构建链路](../../architecture/preview-and-build-flow.md)。

修改此链路时，同时检查 [`preview.py`](../../../../backend/app/api/routes/preview.py)、[`internal_runtime.py`](../../../../backend/app/api/routes/internal_runtime.py)、[`runtime-saas-preview.ts`](../../../../runtime/src/core/plugins/runtime-saas-preview.ts)、[文件鉴权与缓存专题](../../projects/file-storage-auth-cache-plan.md)和部署网关规则。生产 S3、多副本及发布待验收项以[发布检查清单](../../../deployment/release-checklist.md)为准。
