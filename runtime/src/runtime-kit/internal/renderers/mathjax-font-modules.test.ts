/**
 * 文件用途：约束 MathJax 动态字体清单与已安装字体包目录、渲染器加载表三者保持一致，防止漂移。
 */
// @vitest-environment node
import { existsSync, readdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { MATHJAX_SVG_DYNAMIC_FONT_MODULES } from './mathjax-font-modules'
import { svgFontLoaders } from './latex'

const nodeRequire = createRequire(import.meta.url)
const packageRoot = dirname(nodeRequire.resolve('@mathjax/mathjax-newcm-font/package.json'))

describe('MathJax 动态字体清单', () => {
  it('应与已安装字体包的 svg/dynamic 模块一一对应', () => {
    const installed = readdirSync(resolve(packageRoot, 'svg/dynamic'))
      .filter(name => name.endsWith('.js'))
      .map(name => `@mathjax/mathjax-newcm-font/js/svg/dynamic/${name}`)
      .sort()

    expect([...MATHJAX_SVG_DYNAMIC_FONT_MODULES].sort()).toEqual(installed)
  })

  it('每个标识都应通过包 exports 解析到真实模块', () => {
    for (const id of MATHJAX_SVG_DYNAMIC_FONT_MODULES) {
      expect(existsSync(nodeRequire.resolve(id)), id).toBe(true)
    }
  })

  it('渲染器加载表与清单键集合完全一致', () => {
    expect(Object.keys(svgFontLoaders).sort()).toEqual([...MATHJAX_SVG_DYNAMIC_FONT_MODULES].sort())
  })
})
