# Web Presentation CLI (`wp`)

面向 `web-presentation` AI 演示文稿创作平台的官方命令行与 Agent 工具包。

## 安装与快速开始

```bash
# 进入 cli 目录或通过 pip/uv 安装
uv pip install -e ./cli

# 登录并绑定 PAT 令牌
wp login --token wp_pat_xxxxxxxx.yyyyyyyyyyyyyyyy

# 检查环境与连通性
wp doctor

# 查看授权的工作空间并切换当前工作空间
wp workspace list
wp workspace use <workspace_id>

# 常用操作
wp project list
wp page list --project-id <project_id>
wp component list
wp asset list
wp theme list
wp style list
wp validate <page_or_component.vue>
wp build run --project-id <project_id>
```
