// 文件功能：对已通过 C 的候选注入相同选择器故障，保存来源和规则，绝不冒充模型生成错误。
import { readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
const candidate = process.argv[2]
if (!/^(gsap|anime)-(native|builder)$/.test(candidate ?? '')) throw new Error('候选 id 无效')
const directory = resolve('tests/experiments/motion-luna'), path = resolve(directory, 'candidates', `${candidate}.vue`)
const previous = JSON.parse(await readFile(resolve(directory, 'evidence', candidate, 'c0/result.json'), 'utf8'))
const source = await readFile(path, 'utf8'), sha = text => createHash('sha256').update(text).digest('hex')
if (previous.status !== 'passed' || sha(source) !== previous.sourceSha256) throw new Error('只允许对已封存通过 C 的同一候选注入故障')
const count = source.split('.clip-caption').length - 1
if (!count) throw new Error('没有可统一注入的 selector，不能另造不对称故障')
const changed = source.replaceAll('.clip-caption', '.clip-captino')
const log = { candidate, sourceStage: 'c0', originalSha256: sha(source), injectedSha256: sha(changed), rule: '仅将源码 .clip-caption 替换成 .clip-captino', occurrences: count, author: '评测器注入；非 Luna 首次生成错误' }
await writeFile(resolve(directory, 'evidence', candidate, 'injection.json'), `${JSON.stringify(log, null, 2)}\n`, { flag: 'wx' })
await writeFile(path, changed)
console.log(JSON.stringify(log))
