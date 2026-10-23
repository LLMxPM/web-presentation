// 文件功能：生成 G2 八任务固定输入素材，不向任何工作空间写入数据。
import { mkdir, copyFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { buildSpinGlb, buildToneWav } from '../motion-g1/fixtures.mjs'

const root = resolve(import.meta.dirname, '../../..')
const output = resolve(root, '.tmp/web-presentation/motion-g2')
await mkdir(output, { recursive: true })

const cards = [
  { key: 'discover', color: '#1d4ed8', light: '#dbeafe', label: '发现', shape: '<circle cx="320" cy="280" r="138" fill="#60a5fa"/><circle cx="320" cy="280" r="74" fill="#1d4ed8"/>' },
  { key: 'connect', color: '#0f766e', light: '#ccfbf1', label: '连接', shape: '<path d="M160 350 L320 150 L480 350" fill="none" stroke="#0d9488" stroke-width="55" stroke-linecap="round"/><circle cx="160" cy="350" r="48" fill="#0f766e"/><circle cx="480" cy="350" r="48" fill="#0f766e"/>' },
  { key: 'deliver', color: '#b45309', light: '#fef3c7', label: '交付', shape: '<rect x="195" y="165" width="250" height="250" rx="38" fill="#f59e0b"/><path d="M255 285 L305 335 L390 235" fill="none" stroke="white" stroke-width="32" stroke-linecap="round" stroke-linejoin="round"/>' },
]
for (const card of cards) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480"><rect width="640" height="480" rx="32" fill="${card.light}"/>${card.shape}<text x="320" y="446" text-anchor="middle" font-family="sans-serif" font-size="42" font-weight="700" fill="${card.color}">${card.label}</text></svg>`
  await writeFile(resolve(output, `${card.key}.svg`), svg)
}
await writeFile(resolve(output, 'voice.wav'), buildToneWav({ seconds: 3 }))
await writeFile(resolve(output, 'spin.glb'), buildSpinGlb())
await copyFile(resolve(root, 'runtime/public/video/runtime-video-showcase.webm'), resolve(output, 'showcase.webm'))
console.log(`G2 固定素材已写入 ${output}`)
