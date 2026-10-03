/** 文件功能：提供授权权限的中文展示及首批 ChatGPT 回调导航边界。 */

/** 只为服务端返回的 Scope 提供中文标签，不在前端维护第二套有效权限清单。 */
export function oauthScopeLabel(scope: string): string {
  const [entity, action] = scope.split(':')
  const labels: Record<string, string> = {
    workspace: '工作空间', project: '项目', page: '页面', component: '组件',
    asset: '资源', 'design-system': '主题与样式', build: '构建',
  }
  return labels[entity ?? ''] && ['read', 'write'].includes(action ?? '')
    ? `${action === 'write' ? '管理' : '读取'}${labels[entity ?? '']}` : scope
}

/** 仅导航到首批精确回调；授权码只随这次导航交付，不进入本地存储。 */
export function navigateOAuthCallback(redirectUri: string): void {
  const target = new URL(redirectUri)
  if (
    target.origin !== 'https://chatgpt.com'
    || target.pathname !== '/connector_platform_oauth_redirect'
    || target.username || target.password || target.hash
  ) {
    throw new Error('授权回调无效，请从 ChatGPT 重新连接。')
  }
  window.location.assign(redirectUri)
}
