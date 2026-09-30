/** 文件功能：在独立预览副本接收 SFC 子请求时恢复 Vue 描述符，不依赖其它副本的编译缓存。 */
import type { ViteDevServer } from 'vite'
import { buildRemoteModuleId, parseRemoteModuleId } from '../shared/runtime-preview'

/**
 * 调用方必须先验证本次 ctx 票据；仅为 Vue 子请求加载同 artifact/源码主模块。
 * Vue 的 style/template/script loader 需要主模块描述符，跨副本首次请求没有该缓存。
 */
export async function prepareRemoteSfcSubrequest(server: ViteDevServer, url: string): Promise<void> {
  const request = new URL(url, 'http://runtime.local')
  const remote = parseRemoteModuleId(url)
  if (!remote?.previewToken || !remote.modulePath.endsWith('.vue') || !request.searchParams.has('vue')) return
  const main = buildRemoteModuleId(remote.artifactId, remote.modulePath, remote.previewToken)
  await server.transformRequest(main)
}
