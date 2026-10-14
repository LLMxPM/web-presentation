/**
 * 文件功能：集中管理面向桌面智能体（Cursor/Claude）与终端 CLI 的安装、登录与配置提示词及命令生成。
 */

export type CliSkillScope = 'project' | 'global'

/**
 * 获取当前前端运行环境的服务端基础地址（Endpoint）。
 * 优先取当前浏览器 Origin，保证自建、局域网或域名部署时命令参数准确无误。
 * @returns 基础地址 URL
 */
export function resolveCurrentEndpoint(): string {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin
  }
  return 'http://127.0.0.1:8000'
}

/**
 * 生成供桌面智能体（如 Cursor、Claude Desktop、Codex）一键执行的全新安装与配置提示词。
 * 引导智能体按顺序检查 Python、安装 CLI、登录平台并由 CLI 交互引导安装官方 Skill。
 *
 * @param options 配置参数，包含服务端地址与令牌
 * @returns 格式化提示词文本
 */
export function buildAgentInstallPrompt(options: {
  endpoint: string
  token: string
  scope?: CliSkillScope
}): string {
  const { endpoint, token } = options

  return `请帮我配置 Web Presentation 的官方命令行工具与配套智能体技能。请按以下步骤执行：

1. 检查当前本地环境是否有 Python 3.11+，并检查 \`wp\` 命令是否已安装。未安装时优先运行：
   uv tool install web-presentation-cli
   （若当前环境未安装 uv，可使用 pipx install web-presentation-cli）
   安装完成后运行 \`wp --version\` 验证。

2. 连接并登录 Web Presentation 平台：
   wp login --endpoint ${endpoint} --token ${token}

3. 安装官方智能体技能（web-presentation Skill，由 CLI 引导安装位置）：
   wp skill install
   安装完成后运行 \`wp skill status\` 验证安装状态。

4. 运行环境自检：
   wp doctor
   并运行 \`wp workspace list\` 确认当前工作空间已成功接入。

配置完成后请告诉我环境就绪状态，后续幻灯片页面创作我将通过 $web-presentation 技能与你协作。`
}

/**
 * 生成供桌面智能体执行的“更新令牌并重新登录”精简提示词。
 * 适用于本地已安装过 CLI 和 Skill，仅因轮换或失效而更新 PAT 的场景。
 *
 * @param options 配置参数，包含服务端地址与新令牌
 * @returns 格式化提示词文本
 */
export function buildAgentReLoginPrompt(options: {
  endpoint: string
  token: string
}): string {
  const { endpoint, token } = options

  return `我的 Web Presentation 访问令牌已更新，请帮我重新登录平台并验证连通性：

1. 执行登录命令更新凭证：
   wp login --endpoint ${endpoint} --token ${token}

2. 验证身份与连接状态：
   wp whoami
   wp doctor

执行完成后请告诉我当前登录的用户身份与可用工作空间列表。`
}

/**
 * 生成终端手动登录命令。
 *
 * @param endpoint 服务端地址
 * @param token 可选的访问令牌明文
 * @returns 终端命令行字符串
 */
export function buildManualLoginCommand(endpoint: string, token?: string): string {
  if (token) {
    return `wp login --endpoint ${endpoint} --token ${token}`
  }
  return `wp login --endpoint ${endpoint}`
}

/**
 * 生成终端手动安装 Skill 的命令。
 *
 * @param scope 可选的技能安装作用域（省略时由 CLI 交互引导）
 * @returns 命令行字符串
 */
export function buildManualSkillInstallCommand(scope?: CliSkillScope): string {
  if (scope) {
    return `wp skill install --scope ${scope}`
  }
  return 'wp skill install'
}
