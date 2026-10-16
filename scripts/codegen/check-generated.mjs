/** 文件功能：隔离重生成 OpenAPI/API/previewSchema 类型并校验提交产物，失败时不改工作树。 */
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

const root = fileURLToPath(new URL('../../', import.meta.url))
const temporaryRoot = resolve(tmpdir())
const directory = mkdtempSync(join(temporaryRoot, 'wp-codegen-'))
/** 使用参数数组执行确定性生成器，禁止依赖当前运行中的 Backend。 */
function generate(script, args) {
  execFileSync(process.execPath, [join(root, 'scripts/codegen', script), ...args], { cwd: root, stdio: 'inherit' })
}
/** 各生成物对应的重生成命令；漂移报错时给出准确的修复入口。 */
const REGEN_COMMAND_HINTS = [
  { files: ['editor/src/types/openapi.json', 'editor/src/types/api.generated.ts'], command: 'pnpm run codegen:editor-api' },
  {
    files: ['editor/src/types/component-preview.generated.ts', 'runtime/src/core/shared/component-preview.generated.ts'],
    command: 'pnpm run codegen:preview-types',
  },
  {
    files: ['editor/src/types/model-view-options.generated.ts', 'runtime/src/core/shared/model-view-options.generated.ts'],
    command: 'pnpm run codegen:model-view-types',
  },
]
/** 统一换行后比较完整产物，字段类型、必填性和嵌套结构均在检查范围。 */
function verify(actual, committed) {
  const normalize = value => value.replace(/\r\n/g, '\n')
  if (normalize(readFileSync(actual, 'utf8')) !== normalize(readFileSync(join(root, committed), 'utf8'))) {
    const hint = REGEN_COMMAND_HINTS.find(entry => entry.files.includes(committed))?.command
    const guidance = hint ?? REGEN_COMMAND_HINTS.map(entry => entry.command).join(' / ')
    throw new Error(`生成物漂移：${committed}；请运行 ${guidance}`)
  }
}
try {
  const openapi = join(directory, 'openapi.json')
  const api = join(directory, 'api.ts')
  const preview = join(directory, 'preview.ts')
  const modelView = join(directory, 'model-view.ts')
  generate('dump-openapi.mjs', [openapi])
  generate('generate-editor-api-types.mjs', [openapi, api])
  generate('generate-preview-types.mjs', [preview])
  generate('generate-model-view-types.mjs', [modelView])
  verify(openapi, 'editor/src/types/openapi.json')
  verify(api, 'editor/src/types/api.generated.ts')
  verify(preview, 'editor/src/types/component-preview.generated.ts')
  verify(preview, 'runtime/src/core/shared/component-preview.generated.ts')
  verify(modelView, 'editor/src/types/model-view-options.generated.ts')
  verify(modelView, 'runtime/src/core/shared/model-view-options.generated.ts')
  console.log('当前 Backend 与提交契约生成物完全一致')
} finally {
  // 删除前核对绝对父路径与本次固定前缀，只清理 mkdtemp 创建的目录。
  if (dirname(resolve(directory)) !== temporaryRoot || !basename(directory).startsWith('wp-codegen-')) {
    throw new Error('拒绝清理预期临时目录之外的路径')
  }
  rmSync(directory, { recursive: true, force: true })
}
