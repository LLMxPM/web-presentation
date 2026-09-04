<!-- 文件功能：介绍官方命令行工具 wp CLI 的安装、认证配置、多环境 Profile、Agent Skill 一键安装与桌面 Agent 协同创作实战。 -->
# 命令行与外部 Agent 接入指南 (wp CLI)

除了在浏览器 Web 端 Editor 中进行可视化与代码创作，平台还提供了官方跨平台命令行工具 **`wp` CLI**（`web-presentation-cli`）。

- **CLI 开源仓库**：[LLMxPM/web-presentation-agent-kit](https://github.com/LLMxPM/web-presentation-agent-kit)（集中维护 `wp` CLI、共享 API Client 及配套 Agent Skill）
- **PyPI 软件包**：[web-presentation-cli](https://pypi.org/project/web-presentation-cli/)
- **配套 Skill 源码**：[web-presentation Skill](https://github.com/LLMxPM/web-presentation-agent-kit/tree/main/skills/web-presentation)

`wp` CLI 为本地开发者、自动化脚本以及桌面级智能代理（如 Cursor、Claude Code、Codex、GitHub Copilot、WorkBuddy 等）提供了完整的无头创作能力。

---

## 1. 安装 CLI

`wp` CLI 基于 Python 构建，推荐使用现代包管理工具全局安装：

### 1.1 推荐安装方式：`uv`
```bash
# 使用 uv 全局安装独立 CLI 工具
uv tool install web-presentation-cli
```

### 1.2 备选安装方式：`pipx`
```bash
# 使用 pipx 安装
pipx install web-presentation-cli
```

### 1.3 验证安装
安装完成后，在终端中执行：
```bash
wp --version
wp --help
```
若能输出工具版本和子命令列表，说明安装成功。

---

## 2. 认证配置与环境连接

在使用 CLI 之前，需要将其连接到你的私有化部署服务或开发环境，并完成鉴权。

### 2.1 获取个人访问令牌 (PAT)
1. 打开平台 Web 界面并登录；
2. 点击右上角用户头像，进入 **“账户设置”**；
3. 在左侧菜单中选择 **“访问令牌 (PAT)”**（路径 `/account/access-tokens`）；
4. 点击“创建令牌”，输入描述（如 `cursor-desktop`）并设置过期时间；
5. 复制系统生成的完整令牌字符串（格式为 `wp_pat_<id>.<secret>`）。该令牌仅在创建时显示一次，请妥善保存。

### 2.2 登录与 Profile 配置
使用 `wp login` 绑定服务地址与令牌：

```bash
# 连接到局域网 NAS 或私有化服务器
# 注意：--endpoint 必须为服务的 HTTP 根地址，不要在末尾添加 /api/v1 或斜杠
wp login --endpoint http://192.168.1.50:8080 --token wp_pat_xxxxxxxx.yyyyyyyyyyyyyyyy

# 连接到本地开发服务（默认 endpoint 为 http://127.0.0.1:8000）
wp login --token wp_pat_xxxxxxxx.yyyyyyyyyyyyyyyy
```

### 2.3 环境体检医生 (`wp doctor`)
配置完成后，运行环境体检命令确认连通性：
```bash
wp doctor
```
`wp doctor` 会自动检查本地 Python 环境、服务连通性、网络延迟、PAT 有效期以及关联的工作空间权限。

### 2.4 检查当前身份 (`wp whoami`)
```bash
wp whoami
```
输出当前登录用户名、角色（平台管理员或普通成员）以及拥有的能力范围。

### 2.5 多环境与工作空间切换
如果同时维护多个部署环境（如本地测试机与团队 NAS）：
```bash
# 查看所有已保存的环境配置
wp profile list

# 切换使用的环境 Profile
wp profile use nas-prod

# 列出当前账号有权访问的工作空间
wp workspace list

# 锁定默认工作空间 ID
wp workspace use <workspace_id>
```

---

## 3. 一键安装 Agent 官方创作 Skill

为了让 Cursor、Claude Code 等桌面 Agent 能够完全理解平台标准（固定画布规范、Runtime Kit 公开能力、异步 Mutation Job 机制与版本安全），`wp` CLI 随包内置了开箱即用的官方 **`web-presentation` Skill**。

### 3.1 Skill 作用与受支持的 Agent 目录

Skill 会向智能体注入平台标准约束、CLI 工作流与自省指令，引导智能体自主按规范进行页面与组件创作。`wp skill` 支持将 Skill 安装到项目本地（推荐）或当前用户全局目录：

| 兼容 Agent | 项目级安装目录（推荐） | 全局安装目录 | 共享说明 |
| :--- | :--- | :--- | :--- |
| **Codex、Cursor、GitHub Copilot、Gemini CLI、OpenCode** | `.agents/skills/web-presentation` | `~/.agents/skills/web-presentation` | 五款 Agent 统一遵循标准规范，共用该目录，仅安装一份 |
| **Claude Code** | `.claude/skills/web-presentation` | `~/.claude/skills/web-presentation` | 专属目录 |
| **Qoder** | `.qoder/skills/web-presentation` | `~/.qoder/skills/web-presentation` | 专属目录 |
| **WorkBuddy 等桌面应用** | 可通过 `wp skill export` 导出通用标准 ZIP 压缩包手动导入 | - | 适用于支持外部 Skill ZIP 导入的桌面客户端 |

> [!TIP]
> 推荐优先使用**项目级安装**（`--scope project`），Skill 规则仅对当前项目生效，便于随代码仓库纳入版本管理与团队共享。

### 3.2 命令行安装 Skill

#### 交互式引导安装（推荐新手）
进入你的项目根目录，在终端中直接执行：
```bash
wp skill install
```
CLI 会交互式引导你选择安装范围（`1. 全局` 或 `2. 项目 (推荐)`）以及需要启用的 Agent 目标。

#### 命令行直接安装（指定 Agent 与范围）
在自动化脚本或明确目标 Agent 的场景下，可使用参数直接安装：

```bash
# 1. 安装到当前项目下的 Cursor（与 Copilot/Codex/Gemini 共享 .agents/skills）
wp skill install --scope project --agent cursor

# 2. 安装到当前项目下的 Claude Code
wp skill install --scope project --agent claude

# 3. 一键覆盖当前项目内所有受支持的 Agent 目录
wp skill install --scope project --agent all

# 4. 若希望所有项目全局生效，可切换为全局范围
wp skill install --scope global --agent all
```

### 3.3 离线与第三方导入：导出标准 Skill ZIP

对于 WorkBuddy 等支持以 ZIP 格式导入外部 Skill 的桌面工具：

```bash
# 导出根目录包含 SKILL.md 的标准 Skill 压缩包
wp skill export

# 指定输出文件路径
wp skill export --output ./web-presentation-skill.zip
```
导出后，在对应客户端的“扩展 / Skill 导入”面板中选择该 ZIP 文件即可完成载入。

### 3.4 检查、更新与维护 Skill 状态

```bash
# 检查已安装 Skill 的版本、兼容性及本地修改状态
wp skill status --scope project --agent all

# 当升级 wp CLI 后，同步更新项目内的 Skill 到最新版本
wp skill install --scope project --agent all

# 如需彻底卸载项目内的 Skill
wp skill uninstall --scope project --agent all --yes
```

> [!IMPORTANT]
> **安装后生效提示**：完成 Skill 安装或更新后，请**重新加载智能体窗口（如 VS Code / Cursor 的 Reload Window）或新建会话**，以便智能体重新扫描并加载最新的 Skill 定义。

---

## 4. 桌面 Agent 深度创作实战闭环

安装好 Skill 后，你可以直接在本地 IDE（如 Cursor）的 Chat 或 Composer 窗口中与 Agent 协作创作。

典型指令范例：
> *“请使用 wp CLI 在当前项目的项目 5 中创建一页产品核心优势汇报页，使用固定 16:9 画布规范，优先复用工作空间已有的卡片组件，并在创建完成后调用截图复核渲染排版。”*

桌面 Agent 将在后台自动执行以下闭环步骤：

```
[ 1. 环境与规范自省 ]
   ├── wp standards page           (获取页面布局标准、禁止项与必须遵循的规范)
   ├── wp runtime-kit list          (查询平台允许导入的版本化公开组件，如 CanvasFrame.v1)
   └── wp project configuration get (获取当前项目的画布分辨率、主色调与字体)

[ 2. 探索已有资产 ]
   ├── wp component list --scope suggested (查询推荐复用的工作空间组件)
   └── wp asset list               (查询团队已上传的企业免抠 Logo 与图片素材)

[ 3. 本地编写 Vue SFC 页面 ]
   └── Agent 在本地工作区生成符合规范的 Slide.vue 源码

[ 4. 提交后台异步校验与落库 ]
   └── wp page create --project-id 5 --title "核心优势" --content-file ./Slide.vue
       (系统自动提交异步 Mutation Job 并等待编译检查通过)

[ 5. 调起截图与视觉复核 ]
   └── wp page screenshot <page_id>
       (Agent 读取渲染截图，自主复核字号、对齐、换行与色彩表现，完成最终微调)
```

---

## 5. 常用 CLI 命令速查表 (Cheatsheet)

### 5.1 项目与页面管理
```bash
# 列出工作空间内的所有项目
wp project list

# 查询指定项目下的所有页面
wp page list --project-id <project_id>

# 查看指定页面的完整 Vue 源码
wp page source <page_id>

# 本地文件创建新页面
wp page create --project-id <project_id> --title "财务拆解" --content-file ./slide.vue

# 编辑已有页面（带乐观锁版本安全检查）
wp page edit <page_id> --base-version-no 2 --content-file ./slide.vue

# 调起服务端 Chromium 生成并下载当前页面高清截图
wp page screenshot <page_id>
```

### 5.2 组件与设计系统管理
```bash
# 列出工作空间内的组件列表
wp component list

# 校验本地组件代码是否符合规范与 previewSchema 约束
wp component validate --content-file ./MyCard.vue

# 创建新组件
wp component create --name "三列指标卡" --import-identifier "MetricThreeCol" --content-file ./MyCard.vue

# 发布组件当前草稿版本供页面引用
wp component publish <component_id>

# 查看当前工作空间的主题与字体族
wp theme list
wp font list
```

### 5.3 静态资源库管理
```bash
# 查询资源库中的素材
wp asset list

# 上传本地图片或图表到工作空间资源库
wp asset upload --file ./architecture.png --name "系统架构图"
```

### 5.4 异步任务排障与监控
```bash
# 查看指定异步任务状态
wp job get <job_id>

# 等待任务执行完成
wp job wait <job_id>

# 取消正在排队的任务
wp job cancel <job_id>
```

---

## 6. 安全与最佳实践

1. **Token 最小权限与轮换**：为不同的设备或团队成员签发独立的 PAT。如果某台开发机丢失或人员变动，可直接在 Web 端“访问令牌”列表中一键注销对应令牌，而无需重置管理员主账号。
2. **遵守外部接口边界**：`wp` CLI 统一通过 `/api/v1` 外部 REST API 与平台安全交互，请勿试图绕过 CLI 直接连接或修改 Backend 数据库及文件目录。
3. **乐观锁版本控制**：使用 `wp page edit` 时建议始终附带 `--base-version-no`，防止在多人协作或多 Agent 并发修改时意外覆盖同事的新版内容。

---

## 7. 相关资源与文档

- [CLI 独立开源仓库 (web-presentation-agent-kit)](https://github.com/LLMxPM/web-presentation-agent-kit)
- [CLI 与 Agent Skill 快速开始指南 (agent-kit 文档)](https://github.com/LLMxPM/web-presentation-agent-kit/blob/main/docs/getting-started.md)
- [External Agent API v1 契约](../../developer/reference/external-agent-api.md)
- [CLI 主仓集成边界](../../developer/cli.md)
- [AI 协作创作工作流](./ai-assisted-creation.md)

