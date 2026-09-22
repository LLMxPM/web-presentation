/**
 * 文件用途：定义 Runtime 全局 Tailwind 配置，并为页面/组件源码提供设计系统 safelist 兜底。
 * @type {import('tailwindcss').Config}
 */

import typography from '@tailwindcss/typography'

import { runtimeTailwindSafelist } from './src/core/tailwind/runtime-safelist.js'
import { runtimeTailwindTheme } from './src/core/tailwind/runtime-tailwind-theme.js'

export default {
  content: {
    relative: true,
    files: ['./index.html', './src/**/*.{js,ts,vue}'],
  },
  safelist: runtimeTailwindSafelist,
  theme: runtimeTailwindTheme,
  plugins: [
    typography,
  ],
}
