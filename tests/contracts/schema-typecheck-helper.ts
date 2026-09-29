/** 文件功能：对共享契约样本执行真实 TypeScript 语义检查，不以字符串包含替代消费验证。 */
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
const require = createRequire(new URL('../../editor/package.json', import.meta.url))
const ts = require('typescript') as typeof import('../../editor/node_modules/typescript')

/** 在内存中检查样本，使用实际生成文件与标准库；返回所有类型诊断。 */
export function checkTypes(source: string): string[] {
  const filename = fileURLToPath(new URL('./__contract_samples__.ts', import.meta.url)).replace(/\\/g, '/')
  const options = { strict: true, noEmit: true, skipLibCheck: true, target: ts.ScriptTarget.ESNext }
  const host = ts.createCompilerHost(options)
  const read = host.readFile.bind(host)
  host.readFile = path => path === filename ? source : read(path)
  const program = ts.createProgram([filename], options, host)
  return ts.getPreEmitDiagnostics(program).map(item => ts.flattenDiagnosticMessageText(item.messageText, '\n'))
}
