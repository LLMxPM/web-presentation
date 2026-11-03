/** 文件功能：集中维护对外仓库地址，供顶栏 GitHub 入口与开源许可说明复用，避免多处硬编码。 */

const REPOSITORY_ROOT = 'https://github.com/LLMxPM/web-presentation'

/** 仓库主页：顶栏 GitHub 入口与许可弹窗的"在 GitHub 查看"共用。 */
export const REPO_HOME_URL = REPOSITORY_ROOT

/** 主仓库 Apache-2.0 许可证文本地址。 */
export const REPO_LICENSE_URL = `${REPOSITORY_ROOT}/blob/main/LICENSE`

/** runtime 目录 AGPL-3.0-or-later 许可证文本地址。 */
export const REPO_RUNTIME_LICENSE_URL = `${REPOSITORY_ROOT}/blob/main/runtime/LICENSE`

/** 内置字体（思源黑体/宋体、Source Code Pro）的 OFL-1.1 全文与版权声明。 */
export const REPO_FONT_LICENSE_URL = `${REPOSITORY_ROOT}/blob/main/runtime/public/fonts/OFL.txt`
