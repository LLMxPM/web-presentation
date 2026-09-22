/**
 * 文件用途：验证 Runtime 内部资源比例测量逻辑对 Formula 和 Mermaid 的渲染结果处理。
 */

import { describe, expect, it } from 'vitest'

import {
  measureAssetRenderHint,
  measureFormulaAspectRatio,
  measureMermaidAspectRatio,
} from './runtime-asset-render-hint-measurer'

/** Mermaid 动态导入与首次渲染较慢，整包测试并行时放宽单用例超时。 */
const MERMAID_MEASURE_TIMEOUT = 30_000

describe('runtime asset render hint measurer', () => {
  it('应能测量单个 Formula SVG 比例', async () => {
    const ratio = await measureFormulaAspectRatio('E = mc^2')

    expect(ratio).toBeGreaterThan(0)
  })

  it('应能按堆叠语义测量多个 Formula SVG 比例', async () => {
    const ratio = await measureFormulaAspectRatio(String.raw`\[x^2\]\[y^2\]`)

    expect(ratio).toBeGreaterThan(0)
  })

  it('应按 LatexViewer 段间距测量多段 Formula 比例', async () => {
    const content = String.raw`% Adam 配置。
\[
\beta_1=0.9,\qquad
\beta_2=0.98,\qquad
\epsilon=10^{-9}
\]

% Transformer 学习率调度：先 warmup 线性升高，再按 step_num^{-0.5} 衰减。
\[
\operatorname{lrate}
=
d_{\text{model}}^{-0.5}
\cdot
\min\left(
\operatorname{step\_num}^{-0.5},
\operatorname{step\_num}\cdot \operatorname{warmup\_steps}^{-1.5}
\right)
\]

\[
\operatorname{warmup\_steps}=4000
\]

% 训练规模。
\[
\text{base: }100000\text{ steps}\approx 12\text{ hours on 8 P100}
\]

\[
\text{big: }300000\text{ steps}\approx 3.5\text{ days on 8 P100}
\]

% Label smoothing。
\[
\epsilon_{\text{ls}}=0.1
\]`

    const result = await measureAssetRenderHint({
      asset_type: 'formula',
      content,
    })
    const ratioValue = result.aspect_ratio_value as number

    expect(result.ok).toBe(true)
    expect(result.aspect_ratio).not.toBe('100:21')
    expect(ratioValue).toBeGreaterThan(2.2)
    expect(ratioValue).toBeLessThan(3.6)
  })

  it('应能测量 Mermaid SVG 比例', async () => {
    const ratio = await measureMermaidAspectRatio('flowchart TD\n  A --> B')

    expect(ratio).toBeGreaterThan(0)
    expect(ratio).not.toBe(1)
  }, MERMAID_MEASURE_TIMEOUT)

  it('应能测量带中文、多行节点和边标签的 Mermaid 图', async () => {
    const content = String.raw`flowchart TB
    q["Q: Queries"] --> score["矩阵乘法\nQ K^T"]
    k["K: Keys"] --> score
    score --> scale["缩放\n除以 sqrt(d_k)"]
    scale --> mask{"是否 decoder masked self-attention?"}
    mask -- 是 --> add_mask["未来位置加 -inf"]
    mask -- 否 --> no_mask["保持原分数"]
    add_mask --> softmax["Softmax 得到注意力权重"]
    no_mask --> softmax
    softmax --> weighted["与 V 加权求和"]
    v["V: Values"] --> weighted
    weighted --> out["Attention(Q,K,V)"]

    classDef tensor fill:#eef6ff,stroke:#2f6f9f,color:#111;
    classDef op fill:#f7f7f2,stroke:#5f6f52,color:#111;
    classDef decision fill:#fff0d6,stroke:#a56a00,color:#111;
    class q,k,v,out tensor;
    class score,scale,add_mask,no_mask,softmax,weighted op;
    class mask decision;`

    const result = await measureAssetRenderHint({
      asset_type: 'mermaid',
      content,
    })

    expect(result.ok).toBe(true)
    expect(result.aspect_ratio).not.toBe('1:1')
    expect(result.aspect_ratio_value).toEqual(expect.any(Number))
  }, MERMAID_MEASURE_TIMEOUT)

  it('应返回 Backend 期望的比例响应字段', async () => {
    const result = await measureAssetRenderHint({
      asset_type: 'formula',
      content: 'a^2 + b^2 = c^2',
    })

    expect(result.ok).toBe(true)
    expect(result.source).toBe('runtime-svg')
    expect(result.aspect_ratio).toEqual(expect.stringMatching(/^\d+:\d+$/))
    expect(result.aspect_ratio_value).toEqual(expect.any(Number))
  })

  it('Mermaid 渲染失败时应抛出错误', async () => {
    await expect(measureAssetRenderHint({
      asset_type: 'mermaid',
      content: 'flowchart TD\n  A -->',
    })).rejects.toThrow()
  }, MERMAID_MEASURE_TIMEOUT)
})
