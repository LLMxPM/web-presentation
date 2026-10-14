/** 文件用途：按标点与特殊符号数量和字号估算有界的文本宽度余量，容忍字体替换后的引号、括号及数学符号字宽差异。 */

/**
 * 返回标点与数学符号保护宽度（inch）；既有显式换行逐行取最大值，不推断或新增换行。
 * 弯引号按半个 em 预留，全角省略号预留 0.4 em，数学运算符与括号使用较小余量；总量受字号和文本框宽度双重限制。
 */
export function calculatePunctuationWidthGuard(
  text: string,
  fontSizeIn: number,
  boxWidthIn: number,
  isTextShape: boolean,
): number {
  let maximumEm = 0
  for (const line of text.split(/\r\n?|\n/)) {
    let em = 0
    for (const character of line) {
      if ('“”‘’'.includes(character)) em += 0.5
      else if ('⋯…'.includes(character)) em += 0.4
      else if ('"\''.includes(character)) em += 0.15
      else if ('()[]{}'.includes(character)) em += 0.2
      else if ('（）【】《》〈〉「」『』'.includes(character)) em += 0.15
      else if ('+−×÷=±≠≈≤≥'.includes(character)) em += 0.1
    }
    maximumEm = Math.max(maximumEm, em)
  }
  if (maximumEm === 0) return 0
  return Math.min(
    (maximumEm + 0.08) * fontSizeIn,
    2.5 * fontSizeIn,
    boxWidthIn * (isTextShape ? 0.1 : 0.15),
  )
}
