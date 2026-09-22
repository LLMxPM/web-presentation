/**
 * 文件用途：验证 Runtime LaTeX 渲染预处理对公式资源常见写法的兼容能力。
 */

import { describe, expect, it } from 'vitest'

import { normalizeLatexSource, renderLatexToString, splitLatexSource } from './latex'

describe('latex renderer helpers', () => {
  it('应将 equation 环境自动按块级公式渲染，并支持微分宏', async () => {
    const source = String.raw`\begin{equation}
\iiint\limits_{0<x,y,z<1} f(x,y,z)
\dif x \dif y \dif z =
\mathcal{F}(x) = \sum_{k=0}^\infty
\oint_0^1 f_k(x,t), \mathrm{d}t
\end{equation}`

    const html = await renderLatexToString(source, {
      throwOnError: false,
      strict: 'warn',
    })

    expect(html).toContain('mjx-container')
    expect(html).toContain('jax="SVG"')
    expect(html).toContain('data-latex="\\mathrm{d}"')
    expect(html).not.toContain('style="color:#cc0000"')
  })

  it('应识别常见外层数学定界符', () => {
    expect(normalizeLatexSource('$$x^2$$')).toEqual({
      source: 'x^2',
      displayMode: true,
    })
    expect(normalizeLatexSource('\\[x^2\\]')).toEqual({
      source: 'x^2',
      displayMode: true,
    })
    expect(normalizeLatexSource('\\(x^2\\)')).toEqual({
      source: 'x^2',
      displayMode: false,
    })
  })

  it('应忽略 TeX 纯注释并保留转义百分号', async () => {
    expect(splitLatexSource('% 子层结构：说明文字不是公式')).toEqual([])
    expect(await renderLatexToString('% 子层结构：说明文字不是公式')).toBe('')

    expect(normalizeLatexSource(String.raw`x + y % 行尾注释`)).toEqual({
      source: 'x + y',
      displayMode: false,
    })
    expect(normalizeLatexSource(String.raw`\%`)).toEqual({
      source: String.raw`\%`,
      displayMode: false,
    })
  })

  it('应自动切分并渲染多个方括号块级公式', async () => {
    const source = String.raw`\[
\partial_x \partial_y \left[
\frac12 \left( x^2+y^2 \right)^2 + xy
\right]
\]
\[
(a+b)^2=\binom{2}{0}a^2+\binom{2}{1}ab+\binom{2}{2}b^2
\]
\[\genfrac{[}{]}{0pt}{}{n}{1}=(n-1)!\]`

    const segments = splitLatexSource(source)
    const html = await renderLatexToString(source)

    expect(segments).toHaveLength(3)
    expect(segments.every((segment) => segment.displayMode)).toBe(true)
    expect(html.match(/<mjx-container/g)).toHaveLength(3)
    expect(html).not.toContain('\\[')
  })

  it('应兼容 align 环境、单美元内联公式和 diff 微分宏', async () => {
    const source = String.raw`\begin{align}
\overline{a+b} &= \overline a + \overline b \\
\underline a &= (a_0, a_1, a_2, \dots)
\end{align}

$\overleftarrow{a+b}$
$\underleftrightarrow{a-b}$

\[
\mathcal{F}(x) = \sum_{k=0}^\infty
\oint_0^1 f_k(x,t) \,\mathrm{d}t
\]\\
\[ \iiint\limits_{0<x,y,z<1} f(x,y,z)
\diff x \diff y \diff z \]`

    const segments = splitLatexSource(source)
    const html = await renderLatexToString(source)

    expect(segments).toHaveLength(5)
    expect(segments.map((segment) => segment.displayMode)).toEqual([true, false, false, true, true])
    expect(html.match(/<mjx-container/g)).toHaveLength(5)
    expect(html).toContain('data-latex="\\mathrm{d}"')
    expect(html).not.toContain('data-latex="\\\\"')
  })

  it('应自动切分连续的 equation 环境，避免方程结构嵌套错误', async () => {
    const source = String.raw`\begin{equation}
\label{eq17}
T^{+}=\frac{1}{2}\begin{bmatrix}1
 & 0  & 0 & 1  \\
 0  &-1  & 1 & 0  \\
\end{bmatrix}
\end{equation}
\begin{equation}
\label{eq21}
\begin{bmatrix}
 i_{\alpha }^{\ast } \\
 i_{\beta }^{\ast }  \\
 \end{bmatrix}
 =\begin{bmatrix}
v_{f\alpha 1}^{+} &  v_{f\beta 1}^{+}  \\
v_{f\beta 1}^{+}  & -v_{f\alpha 1}^{+} \\
\end{bmatrix}
\begin{bmatrix}
 P_{\rm ref} \\ 0  \\
\end{bmatrix}
\end{equation}`

    const segments = splitLatexSource(source)
    const html = await renderLatexToString(source)

    expect(segments).toHaveLength(2)
    expect(segments.every((segment) => segment.displayMode)).toBe(true)
    expect(html.match(/<mjx-container/g)).toHaveLength(2)
  })
})
