# 预览 artifact 与构建任务

Backend 负责把平台数据转换为 Runtime 可执行的短期上下文和构建快照。

## preview artifact

preview artifact 是 Runtime 预览页面或组件时读取的短期上下文。它应包含当前对象渲染所需的源码、配置、资源引用和访问令牌，不应长期保存。

## 截图任务

截图由 Backend 创建任务并调用 Runtime 执行。需要关注 viewport、超时、并发、visual-ready 等参数，避免截图队列阻塞。

## build snapshot

build snapshot 是一次项目构建的固化输入。构建开始后 Runtime 应基于 snapshot 执行，不应继续读取可能变化的项目状态。

## 构建任务

构建任务记录状态、日志摘要、产物位置和错误信息。失败时应尽量保留可诊断信息，方便区分源码错误、资源缺失、Runtime 不可用和上传失败。

## 产物托管

Runtime 构建完成后把 zip 或静态产物上传回 Backend。Backend 负责保存产物并提供稳定下载或静态访问地址。
