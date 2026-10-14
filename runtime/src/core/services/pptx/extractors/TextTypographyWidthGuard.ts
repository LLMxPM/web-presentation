/** 文件用途：汇总 PPTX 字体替换中的符号、数字与空格字宽差异，按实际文字行计算有界补偿预算。 */

/**
 * 符号预算以 em 为单位；按当前系统字体栈到微软雅黑的实测增幅向上预留。
 * 同族字形共用保守预算；这些参数只容忍字体差异，不承诺各平台字体度量完全相同。
 */
const SYMBOL_WIDTH_GUARDS: ReadonlyArray<readonly [string, number]> = [
  ['“”', 0.7],
  ['‘’', 0.85],
  ['⋯…', 0.4],
  ['"\'', 0.15],
  ['«»‹›', 0.08],
  ['()[]{}', 0.2],
  ['（）【】《》〈〉「」『』', 0.15],
  ['—‒', 0.12],
  ['–‐‑-', 0.06],
  ['∶', 0.7],
  ['↗↖↘↙', 0.3],
  ['→←↑↓↔⇒⇐⇔↦⟶⟵', 0.2],
  ['+−×÷=±≠≈≤≥∑∏√∞∫∈∉⊂⊆∪∩∧∨≡≅≃≪≫∝∠∷∴∵⊕⊗', 0.1],
  ['<>~^', 0.08],
  ['%', 0.1],
  ['‰‱', 0.15],
  ['.,;:!?/\\|·•∙●▪°′″#*_§¶†‡', 0.06],
  ['$¥€£¢¤', 0.07],
  ['©®™&@', 0.1],
  ['№', 0.14],
]

const SYMBOL_WIDTH_GUARD_EM = new Map(
  SYMBOL_WIDTH_GUARDS.flatMap(([characters, guard]) => Array.from(characters, character => [character, guard] as const)),
)
const NUMERIC_WIDTH_GUARD_EM = 0.06
const SPACE_WIDTH_GUARD_EM = 0.03

/** 累加同一行的独立字宽差异；普通中文和稳定的全角标点不额外计费。 */
function calculateLineWidthGuardEm(line: string): number {
  let guardEm = 0
  for (const character of line) {
    if (character >= '0' && character <= '9') guardEm += NUMERIC_WIDTH_GUARD_EM
    else if (character === ' ' || character === '\u00a0' || character === '\u202f') guardEm += SPACE_WIDTH_GUARD_EM
    else guardEm += SYMBOL_WIDTH_GUARD_EM.get(character) ?? 0
  }
  return guardEm
}

/**
 * 返回字体替换补偿（inch）：同一行的符号、数字与空格先相加，多行只取最大行。
 * 总量不超过 2.5em，且最多占普通文本框宽度的 15% 或文本形状宽度的 10%。
 * 调用方必须先确认实际单行，并进一步约束容器、相邻图元及胶囊的可用空间。
 */
export function calculateTextTypographyWidthGuard(
  text: string,
  fontSizeIn: number,
  boxWidthIn: number,
  isTextShape: boolean,
): number {
  let maximumEm = 0
  for (const line of text.split(/\r\n?|\n/)) maximumEm = Math.max(maximumEm, calculateLineWidthGuardEm(line))
  if (maximumEm === 0) return 0
  return Math.min(
    (maximumEm + 0.08) * fontSizeIn,
    2.5 * fontSizeIn,
    boxWidthIn * (isTextShape ? 0.1 : 0.15),
  )
}
