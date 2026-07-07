# 预览与构建链路

预览与构建是 Backend、Editor、Runtime 的核心协作链路。两条链路都以 Backend 为控制面，以 Runtime 为执行面。

## 页面预览

1. Editor 保存页面源码或配置。
2. Backend 校验用户权限和源码导入边界。
3. Backend 创建 preview artifact，并为 Runtime 签发短期上下文令牌。
4. Editor iframe 访问 Runtime 预览入口。
5. Runtime 回源 Backend 读取上下文、配置包、资源和远程模块。
6. Runtime 渲染页面并把结果展示给 Editor。

## 组件预览

组件预览依赖组件源码和 previewSchema。Backend 负责校验 previewSchema 可导入能力，Runtime 负责按 schema 渲染典型状态。previewSchema 变化时要同步 Runtime 组件预览测试和 Backend 契约测试。

## 截图

截图由 Backend 调度，Runtime 使用浏览器执行渲染并返回截图结果。截图任务需要关注 viewport、超时、并发、资源加载和页面 visual-ready 状态。

## 项目构建

1. 用户在 Editor 发起项目构建。
2. Backend 创建构建任务和 build snapshot。
3. Runtime 拉取 snapshot，生成临时入口并执行 Vite 构建。
4. Runtime 将构建产物压缩并上传回 Backend。
5. Backend 保存产物并返回稳定访问地址。

## 关键约束

- 页面源码、组件源码和 previewSchema 只能引用 Runtime Kit manifest 公开且版本化的能力。
- Runtime shell 内部能力不进入页面、组件或 AI 能力目录。
- 构建 snapshot 应固化当次构建所需上下文，避免构建过程中读取漂移状态。
- 预览 artifact 和构建心跳属于临时运行态，应有 TTL 和恢复策略。
