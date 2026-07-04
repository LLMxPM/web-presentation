# 备份与恢复

生产环境备份应覆盖数据库、资源文件、构建产物和密钥。只备份容器镜像不足以恢复平台状态。

## 必备备份

- PostgreSQL：用户、工作空间、项目、页面、资产元数据、AI 会话和构建任务。
- 资源存储：local 模式下的 `backend-data` volume，或 S3 bucket。
- 构建产物：Backend 托管的 build artifacts。
- 密钥：`AI_SECRET_ENCRYPTION_KEY`、数据库密码、Redis 密码和对象存储凭证。

## AI 密钥

`AI_SECRET_ENCRYPTION_KEY` 用于加密用户模型凭证。恢复环境必须使用同一个值，否则历史凭证无法解密。

## local 存储

local 模式会把资源写入 Backend 数据 volume。备份数据库时，也要备份对应 volume 或挂载目录。

## S3 存储

S3 模式下，数据库保存元数据，文件保存在 bucket。恢复时需要确保 bucket、访问凭证和 `S3_PUBLIC_BASE_URL` 与部署配置一致。

## 恢复顺序

1. 恢复数据库。
2. 恢复资源和构建产物。
3. 恢复 `.env` 和密钥。
4. 启动与数据库 revision 匹配的平台镜像。
5. 验证登录、资源访问、预览、截图、构建和 AI 设置。
