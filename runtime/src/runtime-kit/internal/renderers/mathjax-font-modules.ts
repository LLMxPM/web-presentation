/**
 * 文件用途：集中登记 MathJax NewCM 按需加载的 SVG 动态字体模块标识。
 *
 * 该清单同时是两处的唯一事实源：
 * 1. `latex.ts` 的 `mathjax.asyncLoad` 加载器键集合（供浏览器按需 import chunk）；
 * 2. `core/plugins/runtime-dependency-optimization.ts` 的 Vite 预打包清单。
 *
 * 两者必须是同一批模块：`@mathjax/src` 在 include 名单里被预打包，而动态字体模块若留在
 * 预打包边界之外，会重新实例化一份字体基类与 `mathjax` 单例。此时 `dynamicSetup` 会把字形
 * 数据写进已废弃的副本，真正的 OutputJax 实例拿不到字形，先被标记 `failed`，随后所有涉及该
 * 字体的公式都会抛 `dynamic file 'xxx' failed to load` 并整条空白。
 *
 * 因此新增/升级字体文件时必须同步本清单（`mathjax-font-modules.test.ts` 会比对已安装包的
 * `svg/dynamic` 目录，漂移即失败）。本文件只允许导出纯字符串常量，不得引入 MathJax 运行时，
 * 否则 Vite 配置进程会被拖入浏览器依赖图。
 */

export const MATHJAX_SVG_DYNAMIC_FONT_MODULES = [
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/accents-b-i.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/accents.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/arabic.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/arrows.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/braille-d.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/braille.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/calligraphic.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/cherokee.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/cyrillic-ss.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/cyrillic.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/devanagari.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/double-struck.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/fraktur.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/greek-ss.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/greek.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/hebrew.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/latin-b.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/latin-bi.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/latin-i.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/latin.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/marrows.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/math.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/monospace-ex.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/monospace-l.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/monospace.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/mshapes.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/phonetics-ss.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/phonetics.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/PUA.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-b.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-bi.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-ex.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-i.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif-r.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/sans-serif.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/script.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/shapes.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/symbols-b-i.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/symbols.js',
  '@mathjax/mathjax-newcm-font/js/svg/dynamic/variants.js',
] as const

/** 单个 MathJax NewCM 动态字体模块标识。 */
export type MathjaxSvgDynamicFontModule = (typeof MATHJAX_SVG_DYNAMIC_FONT_MODULES)[number]
