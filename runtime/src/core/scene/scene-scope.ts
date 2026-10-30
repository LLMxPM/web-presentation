/** 文件功能：判断 Scene 根是否属于静态作用域，供正式宿主、单页预览与调试共用。 */

/** 任一祖先的静态策略都禁止播放，不能借外层交互策略放宽缩略图。 */
export function isStaticSceneRoot(root: HTMLElement): boolean {
  return Boolean(root.closest('[data-runtime-execution="capture"], [data-runtime-execution="export"], [data-runtime-execution="thumbnail"]'))
}
