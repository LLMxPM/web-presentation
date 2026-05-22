<!-- 文件功能：说明页面管理一期前端工作台的依赖安装、启动与测试方式。 -->
# Editor

`editor/` 是页面管理一期管理后台前端，负责：

- 用户登录页
- 工作空间管理页与成员隔离后的资源入口
- 项目管理页
- 页面资源库管理页
- 账户 AI 设置页
- 平台管理员用户管理页

## 1. 安装依赖

```powershell
pnpm install
```

## 2. 配置后端地址

默认情况下，前端会请求同源 `/api`，并由 Vite 开发服务器代理到本地后台，避免因为 `localhost` 和 `127.0.0.1` 混用导致 Cookie 无法回传、登录后接口全部 `401`。

推荐在本地开发时使用：

```powershell
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

如需统一前端时间展示和 Runtime 预览目录日期，请同时配置业务时区：

```powershell
VITE_APP_TIMEZONE=Asia/Shanghai
```

如需显式直连其它网关或反向代理地址，也可以覆盖接口前缀：

```powershell
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

如果使用 `VITE_API_BASE_URL` 直连后端，请确保编辑器页面与后端接口处于同站上下文，或由部署层正确处理跨站 Cookie；否则登录成功后，后续受保护接口仍可能返回 `401`。

说明：

- `VITE_APP_TIMEZONE` 应与 Backend 的 `APP_TIMEZONE` 保持一致
- 页面列表时间、版本历史时间、Runtime 预览日期目录都会按该业务时区处理

## 3. 多用户入口

Editor 默认请求同源 `/api`。登录后根据当前用户角色展示能力：

- `platform_admin` 可在用户菜单进入“用户管理”，创建用户、重置密码、启用/禁用用户和调整角色
- `workspace_user` 只能看到自己是成员的工作空间和资源
- 账号 AI 设置中会同时展示管理员全局模型与个人模型；全局模型普通用户只可选择绑定，不可编辑

## 4. 启动与验证

启动开发服务：

```powershell
pnpm dev
```

构建检查：

```powershell
pnpm build
```

运行前端测试：

```powershell
pnpm test
```
