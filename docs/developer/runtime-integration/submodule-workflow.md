# Runtime 子模块协作

`runtime/` 是独立项目 `web-runtime-vue` 的 Git 子模块。根仓不直接拥有 Runtime 的完整开发节奏。

## 推荐流程

1. 在 `web-runtime-vue` 上游仓库完成能力开发。
2. 运行 Runtime 自身类型检查、测试和构建。
3. 发布 Runtime Docker 镜像，至少包含 `sha-<runtime_sha_short>` 标签。
4. 回到根仓更新 `runtime` 子模块指针。
5. 运行根仓 Runtime 契约测试和相关 gate。
6. 更新根仓文档和部署说明。

## 镜像约束

平台 Release 前应确认当前 Runtime 子模块 SHA 对应镜像存在：

```bash
docker buildx imagetools inspect docker.io/llmxpm/web-runtime-vue:sha-<runtime_sha_short>
```

## 文档联动

Runtime 接口、环境变量、manifest、构建产物或镜像标签策略变化时，需要同步更新本目录和 Runtime 自身文档。
