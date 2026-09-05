# 命令行与外部 Agent 创作 (CLI)

除了在 Web 端 Editor 中创作，平台还提供了官方命令行工具 `wp` CLI（`web-presentation-cli`），支持在本地终端、IDE 或通过外部桌面 Agent（如 Cursor、Claude Desktop、Codex 等）直接操作工作空间资产、生成页面并复核渲染。

---

## 1. 适用场景

- **桌面 Agent 深度创作**：让本地 Agent 基于固定画布、组件规范与资源清单，自主编写 Vue SFC 页面源码并通过异步任务完成编译与截图复核。
- **本地终端与脚本自动化**：在终端快速查询项目结构、批量导出/更新页面、维护工作空间资源或设计系统。
- **无头环境与流水线集成**：在不需要打开浏览器的场景下，通过标准 External API v1 驱动页面变更。

---

## 2. 安装 CLI

推荐使用 `uv` 或 `pipx` 全局安装官方发布版：

```bash
# 使用 uv 安装（推荐）
uv tool install web-presentation-cli

# 或使用 pipx
pipx install web-presentation-cli
```

安装后在终端验证：

```bash
wp --help
```

---

## 3. 认证与工作空间配置

### 3.1 获取个人访问令牌 (PAT)

1. 登录平台 Web 界面。
2. 进入“账户设置” → “访问令牌 (PAT)”，选择有效期限、授权工作空间与权限 Scope，新建并复制生成的密钥（形如 `wp_pat_xxxxxxxx.yyyyyyyyyyyyyyyy`）。有效期限可选择“长期有效”；工作空间可授权指定空间，或动态授权当前及未来加入的所有工作空间。

长期、全工作空间 PAT 适合受控的个人开发环境。共享机器和 CI 建议按最小权限选择指定工作空间与有限有效期，并在不再使用时及时吊销。

### 3.2 登录与连通性检查

使用 `wp login` 绑定服务地址与令牌：

```bash
# 本地开发环境（默认 http://127.0.0.1:8000）
wp login --token wp_pat_xxxxxxxx.yyyyyyyyyyyyyyyy

# 自建服务或生产环境（指定服务根地址，不要包含 /api/v1）
wp login --endpoint http://192.168.1.20:8080 --token wp_pat_xxxxxxxx.yyyyyyyyyyyyyyyy
```

检查环境连通性：

```bash
wp doctor
```

### 3.3 切换当前工作空间

```bash
# 列出有权限的工作空间
wp workspace list

# 切换并锁定当前工作空间
wp workspace use <workspace_id>
```

---

## 4. 常用操作速查

### 4.1 项目与页面查询

```bash
# 列出工作空间内的项目
wp project list

# 查询项目展示配置（画布尺寸、基础字号、主题等）
wp project configuration get <project_id>

# 列出项目下的所有页面
wp page list --project-id <project_id>

# 读取指定页面的源码
wp page source <page_id>
```

### 4.2 规范与运行时能力自省

在编写页面或组件前，可先读取平台当前的动态规范与可导入能力：

```bash
# 获取页面代码规范与约束
wp standards page

# 获取组件代码规范
wp standards component

# 查看 Runtime Kit 公开能力列表（如画布、资源渲染组件等）
wp runtime-kit list
```

### 4.3 页面创建与结构化编辑

页面创建和源码修改会自动提交到后台异步任务，并在完成编译检查后落库：

```bash
# 从本地 Vue 文件创建新页面
wp page create --project-id <project_id> --title "产品架构" --content-file ./architecture.vue

# 编辑已有页面（带乐观锁版本检查）
wp page edit <page_id> --base-version-no <current_version> --content-file ./architecture.vue

# 生成并获取页面最新截图
wp page screenshot <page_id>
```

### 4.4 资源与组件管理

```bash
# 查询工作空间资源库
wp asset list

# 上传新图片或图表资源
wp asset upload --file ./diagram.png --name "系统架构图"

# 查询建议复用的工作空间组件
wp component list --scope suggested --project-id <project_id>
```

---

## 5. 配合外部 Agent 与 Skill 创作

对于使用 Claude Desktop、Cursor、Codex 等桌面 Agent 的场景，推荐配合官方配套的 `web-presentation` Skill 一起使用：

1. **Skill 来源**：位于同级独立仓库 [web-presentation-agent-kit/skills/web-presentation](https://github.com/LLMxPM/web-presentation-agent-kit/tree/main/skills/web-presentation)。
2. **闭环工作流**：
   - **构思与设计**：Agent 依据 `wp standards page` 和项目画布尺寸进行版面构图；
   - **资产引用**：查询已发布组件与资源 `name`，通过 `@runtime-kit/...` 引用运行时能力；
   - **提交变更**：调用 `wp page edit` 触发后台任务；
   - **截图验证**：调用 `wp page screenshot` 复核真实渲染效果与文字排版。

---

## 6. 相关文档

- [CLI 外部接入仓库 (web-presentation-agent-kit)](https://github.com/LLMxPM/web-presentation-agent-kit)
- [External Agent API v1 契约](../../developer/reference/external-agent-api.md)
- [CLI 主仓集成边界](../../developer/cli.md)
- [AI 协作创作工作流](./ai-assisted-creation.md)
