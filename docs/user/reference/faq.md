# 常见问题

## 项目网站在哪里？

项目网站是 [https://llmxpm.github.io/web-presentation-site/](https://llmxpm.github.io/web-presentation-site/)，适合先浏览产品介绍、截图和演示入口。

## 公开 Demo 在哪里？

访问方式、账号和推荐体验流程见 [Demo 使用指南](../demo-guide.md)。

## 我只想体验，需要部署吗？

不需要。先使用公开 Demo 或本地开发环境体验；需要团队自托管时再阅读 [自托管部署](../deployment.md)。

## 自托管应该选哪种部署方式？

个人或小团队优先使用 SQLite 轻量单容器部署，一个容器内运行 Backend、Runtime 和 Gateway，不需要额外准备 PostgreSQL 和 Redis。需要长期生产使用、集中备份、对象存储或现有数据库基础设施时，再阅读 [生产部署指南](../../developer/deployment/README.md)。

## 默认管理员密码在哪里改？

SQLite 轻量单容器版和简化版直接在对应 compose 文件中修改 `DEFAULT_ADMIN_PASSWORD`。首次启动前必须替换默认值，正式使用后建议创建个人账号并配置工作空间权限。

## 自托管数据保存在哪里？

SQLite 轻量单容器版的数据保存在 `lite-data` volume 中，包括 SQLite 数据库、本地资源、截图、构建产物和 Runtime RSA 私钥。备份时应完整备份该 volume，不要只复制数据库文件。

## AI_SECRET_ENCRYPTION_KEY 是什么？

它是用于加密用户模型凭证的 Fernet 密钥，不是模型 API Key。部署前必须生成新的 32 字节随机 URL-safe base64 值并长期保存；更换该值会导致已保存的用户模型凭证无法解密。

## AI 设置保存后不生效怎么办？

先确认账户 AI 设置中模型供应商、模型名、API Key 和 Base URL 是否完整，再确认 Backend 的加密密钥没有变化。生产排障见 [部署排障](../../developer/deployment/troubleshooting.md)。

## 页面预览空白怎么办？

先检查页面源码是否报错，再检查资源、组件和 Runtime Kit 引用是否存在。用户侧流程见 [预览、截图与构建](../workflows/preview-build-export.md)。

## 可以删除已被引用的资源吗？

不建议。删除前先检查引用关系。仍被页面、组件、主题或字体注册引用的资源，优先归档或替换。

## 组件什么时候应该发布新版本？

当组件行为、参数、视觉结构或依赖发生可能影响旧页面的变化时，应发布新版本，并让页面按需升级。
