/** 文件功能：从路由目录构建演讲页面及备注，隐藏页不进入导航列表。 */
import type { RouteConfig } from '@/core/types/navigation'
import { normalizePresenterRoutePath } from './presenter-url'
export interface PresenterPage { path: string; title: string; pageNumber: number; componentPath: string; speakerNotes: string }
/** 展平页面目录，只保留已分配页码的可见叶子。 */
export function buildPresenterPages(configs: RouteConfig[]): PresenterPage[] {
  const pages: PresenterPage[] = []
  for (const route of configs) {
    if (route.children?.length) {
      for (const child of route.children) {
        appendPresenterPage(pages, child, `/${route.path}/${child.path}`)
      }
      continue
    }
    appendPresenterPage(pages, route, `/${route.path}`)
  }
  return pages.sort((left, right) => left.pageNumber - right.pageNumber)
}

/**
 * 把单个 Runtime 路由追加为演讲页。
 * @param target 目标列表
 * @param route 路由配置
 * @param path 页面路径
 */
function appendPresenterPage(target: PresenterPage[], route: RouteConfig, path: string): void {
  if (route.meta?.hidden || route.pageNumber === undefined) {
    return
  }
  const componentPath = typeof route.meta?.componentPath === 'string' ? route.meta.componentPath : ''
  const speakerNotes = typeof route.meta?.speakerNotes === 'string' ? route.meta.speakerNotes : ''
  target.push({
    path: normalizePresenterRoutePath(path.replace(/\/+/g, '/')),
    title: route.title,
    pageNumber: route.pageNumber,
    componentPath,
    speakerNotes,
  })
}

