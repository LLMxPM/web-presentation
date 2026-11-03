/**
 * 文件功能：开源许可弹窗的展示数据，声明本项目自身许可，并按作用分组列出平台直接依赖的开源项目。
 * 维护约定：新增直接依赖时同步补充到对应分组；非 OSI 认可协议或特殊授权条件的条目只填 note，
 * 由弹窗以 Tooltip 呈现，不得在列表中展开成正文。
 */

import { REPO_FONT_LICENSE_URL, REPO_LICENSE_URL, REPO_RUNTIME_LICENSE_URL } from '@/utils/repo-links'

export interface ProjectLicenseEntry {
  /** 稳定标识，用于列表 key。 */
  key: string
  /** 授权范围名称。 */
  title: string
  /** 许可证名称。 */
  license: string
  /** 许可证全文地址。 */
  href: string
}

export interface OpenSourceNoticeItem {
  /** 项目或库的展示名称。 */
  name: string
  /** 许可证简称。 */
  license: string
  /** 需要额外说明的授权条件，仅通过 Tooltip 展示。 */
  note?: string
  /** 许可证全文或官方说明地址；有值时名称渲染为链接。 */
  href?: string
}

export interface OpenSourceNoticeGroup {
  /** 稳定标识，同时作为标签页 value。 */
  key: string
  /** 该分组在平台中承担的作用。 */
  title: string
  items: OpenSourceNoticeItem[]
}

/** 本项目自身的许可声明：主仓库与 runtime 目录分别授权。 */
export const PROJECT_LICENSES: ProjectLicenseEntry[] = [
  {
    key: 'platform',
    title: '主仓库',
    license: 'Apache License 2.0',
    href: REPO_LICENSE_URL,
  },
  {
    key: 'runtime',
    title: 'runtime/ 目录',
    license: 'AGPL-3.0-or-later',
    href: REPO_RUNTIME_LICENSE_URL,
  },
]

/** 平台直接依赖的开源项目，按承担的作用分组。 */
export const OPEN_SOURCE_GROUPS: OpenSourceNoticeGroup[] = [
  {
    key: 'ui',
    title: '界面与编辑',
    items: [
      { name: 'Vue 3', license: 'MIT' },
      { name: 'Vue Router', license: 'MIT' },
      { name: 'Pinia', license: 'MIT' },
      { name: 'TanStack Query', license: 'MIT' },
      { name: 'Reka UI', license: 'MIT' },
      { name: 'Tailwind CSS', license: 'MIT' },
      { name: 'tailwind-merge', license: 'MIT' },
      { name: 'Lucide', license: 'ISC' },
      { name: 'Monaco Editor', license: 'MIT' },
      { name: 'Markstream', license: 'MIT' },
      { name: 'Axios', license: 'MIT' },
    ],
  },
  {
    key: 'render',
    title: '渲染与导出',
    items: [
      { name: 'ECharts', license: 'Apache-2.0' },
      { name: 'Three.js', license: 'MIT' },
      { name: 'Mermaid', license: 'MIT' },
      {
        name: 'GSAP',
        license: '自定义许可',
        note: '采用 GSAP 标准免费许可，不属于 OSI 定义的开源协议，商用分发前需按该许可确认适用场景。',
      },
      { name: 'svg-pan-zoom', license: 'BSD-2-Clause' },
      { name: 'SnapDOM', license: 'MIT' },
      { name: 'PptxGenJS', license: 'MIT' },
      { name: 'jsPDF', license: 'MIT' },
      { name: 'fflate', license: 'MIT' },
      { name: 'MathJax', license: 'Apache-2.0' },
    ],
  },
  {
    key: 'server',
    title: '服务端与数据',
    items: [
      { name: 'FastAPI', license: 'MIT' },
      { name: 'Starlette', license: 'BSD-3-Clause' },
      { name: 'Uvicorn', license: 'BSD-3-Clause' },
      { name: 'SQLAlchemy', license: 'MIT' },
      { name: 'Alembic', license: 'MIT' },
      { name: 'Pydantic', license: 'MIT' },
      { name: 'asyncpg', license: 'Apache-2.0' },
      {
        name: 'psycopg',
        license: 'LGPL-3.0',
        note: '以未修改源码的动态链接方式使用，分发时需保留可替换性。',
      },
      { name: 'redis-py', license: 'MIT' },
      { name: 'aiosqlite', license: 'MIT' },
    ],
  },
  {
    key: 'ai',
    title: '智能体与模型',
    items: [
      { name: 'Pydantic AI', license: 'MIT' },
      { name: 'OpenAI Python SDK', license: 'Apache-2.0' },
      { name: 'Google Gen AI SDK', license: 'Apache-2.0' },
      { name: 'Ollama SDK', license: 'MIT' },
      { name: 'tiktoken', license: 'MIT' },
    ],
  },
  {
    key: 'assets',
    title: '字体与素材',
    items: [
      {
        name: '思源黑体 / 思源宋体',
        license: 'OFL-1.1',
        href: REPO_FONT_LICENSE_URL,
        note: 'OFL 要求再分发时附带许可证全文，仓库内 OFL.txt 已收录。',
      },
      {
        name: 'Source Code Pro',
        license: 'OFL-1.1',
        href: REPO_FONT_LICENSE_URL,
        note: 'OFL 要求再分发时附带许可证全文，仓库内 OFL.txt 已收录。',
      },
      {
        name: 'glTF 示例模型',
        license: 'CC BY 4.0',
        note: '仅用于本地演示 fixture，署名与来源见 runtime/public/model/ATTRIBUTION.md。',
      },
    ],
  },
  {
    key: 'tooling',
    title: '工具链',
    items: [
      { name: 'Vite', license: 'MIT' },
      { name: 'Vitest', license: 'MIT' },
      { name: 'Playwright', license: 'Apache-2.0' },
      { name: 'TypeScript', license: 'Apache-2.0' },
      { name: 'pytest', license: 'MIT' },
      { name: 'Ruff', license: 'MIT' },
    ],
  },
]
