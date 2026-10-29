/** 文件功能：按路由发现放映主画布根节点，供现有宿主和 Scene 准备共用。 */

/** 只匹配带平台路由标记的页面，不误取缩略图或其它过渡层。 */
export function findPlaybackPageElement(path: string): HTMLElement | null {
  if (typeof document === 'undefined') return null
  return Array.from(document.querySelectorAll<HTMLElement>('.runtime-page-print-source'))
    .find(element => element.dataset.runtimeRoutePath === path) ?? null
}
