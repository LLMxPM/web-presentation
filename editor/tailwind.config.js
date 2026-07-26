/**
 * 文件功能：将 Editor 语义化 Design Token 映射为 Tailwind 工具类。
 */

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: 'rgb(var(--ui-canvas) / <alpha-value>)',
        overlay: 'rgb(var(--ui-overlay) / <alpha-value>)',
        surface: {
          DEFAULT: 'rgb(var(--ui-surface) / <alpha-value>)',
          raised: 'rgb(var(--ui-surface-raised) / <alpha-value>)',
          muted: 'rgb(var(--ui-surface-muted) / <alpha-value>)',
          hover: 'rgb(var(--ui-surface-hover) / <alpha-value>)',
          selected: 'rgb(var(--ui-surface-selected) / <alpha-value>)',
          inverse: 'rgb(var(--ui-surface-inverse) / <alpha-value>)',
          'inverse-raised': 'rgb(var(--ui-surface-inverse-raised) / <alpha-value>)',
        },
        text: {
          DEFAULT: 'rgb(var(--ui-text) / <alpha-value>)',
          strong: 'rgb(var(--ui-text-strong) / <alpha-value>)',
          emphasis: 'rgb(var(--ui-text-emphasis) / <alpha-value>)',
          secondary: 'rgb(var(--ui-text-secondary) / <alpha-value>)',
          muted: 'rgb(var(--ui-text-muted) / <alpha-value>)',
          disabled: 'rgb(var(--ui-text-disabled) / <alpha-value>)',
          faint: 'rgb(var(--ui-text-faint) / <alpha-value>)',
          inverse: 'rgb(var(--ui-text-inverse) / <alpha-value>)',
          'on-inverse': 'rgb(var(--ui-text-on-inverse) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--ui-border) / <alpha-value>)',
          muted: 'rgb(var(--ui-border-muted) / <alpha-value>)',
          strong: 'rgb(var(--ui-border-strong) / <alpha-value>)',
          focus: 'rgb(var(--ui-border-focus) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--ui-accent) / <alpha-value>)',
          hover: 'rgb(var(--ui-accent-hover) / <alpha-value>)',
          emphasis: 'rgb(var(--ui-accent-emphasis) / <alpha-value>)',
          border: 'rgb(var(--ui-accent-border) / <alpha-value>)',
          ring: 'rgb(var(--ui-accent-ring) / <alpha-value>)',
          muted: 'rgb(var(--ui-accent-muted) / <alpha-value>)',
        },
        danger: {
          DEFAULT: 'rgb(var(--ui-danger) / <alpha-value>)',
          strong: 'rgb(var(--ui-danger-strong) / <alpha-value>)',
          border: 'rgb(var(--ui-danger-border) / <alpha-value>)',
          muted: 'rgb(var(--ui-danger-muted) / <alpha-value>)',
        },
        warning: {
          DEFAULT: 'rgb(var(--ui-warning) / <alpha-value>)',
          strong: 'rgb(var(--ui-warning-strong) / <alpha-value>)',
          border: 'rgb(var(--ui-warning-border) / <alpha-value>)',
          muted: 'rgb(var(--ui-warning-muted) / <alpha-value>)',
        },
        success: {
          DEFAULT: 'rgb(var(--ui-success) / <alpha-value>)',
          strong: 'rgb(var(--ui-success-strong) / <alpha-value>)',
          border: 'rgb(var(--ui-success-border) / <alpha-value>)',
          muted: 'rgb(var(--ui-success-muted) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'rgb(var(--ui-info) / <alpha-value>)',
          strong: 'rgb(var(--ui-info-strong) / <alpha-value>)',
          border: 'rgb(var(--ui-info-border) / <alpha-value>)',
          muted: 'rgb(var(--ui-info-muted) / <alpha-value>)',
        },
        ai: {
          DEFAULT: 'rgb(var(--ui-ai) / <alpha-value>)',
          strong: 'rgb(var(--ui-ai-strong) / <alpha-value>)',
          border: 'rgb(var(--ui-ai-border) / <alpha-value>)',
          muted: 'rgb(var(--ui-ai-muted) / <alpha-value>)',
        },
      },
      /*
       * 裸写 border/divide（不带颜色）默认走语义边框 Token，
       * 避免回退到 Tailwind 默认 gray-200 导致夜间模式出现亮色分割线。
       */
      borderColor: {
        DEFAULT: 'rgb(var(--ui-border) / <alpha-value>)',
      },
      divideColor: {
        DEFAULT: 'rgb(var(--ui-border) / <alpha-value>)',
      },
      borderRadius: {
        'ui-sm': 'var(--ui-radius-sm)',
        'ui-md': 'var(--ui-radius-md)',
        'ui-lg': 'var(--ui-radius-lg)',
        'ui-xl': 'var(--ui-radius-xl)',
      },
      spacing: {
        'control-xs': 'var(--ui-control-h-xs)',
        'control-sm': 'var(--ui-control-h-sm)',
        'control-md': 'var(--ui-control-h-md)',
        'control-lg': 'var(--ui-control-h-lg)',
        'icon-sm': 'var(--ui-icon-sm)',
        'icon-md': 'var(--ui-icon-md)',
        'icon-lg': 'var(--ui-icon-lg)',
      },
      fontFamily: {
        sans: ['var(--ui-font-sans)'],
        mono: ['var(--ui-font-mono)'],
      },
      fontSize: {
        'title-sm': ['1rem', { lineHeight: '1.5rem', fontWeight: '600' }],
        'title-md': ['1.25rem', { lineHeight: '1.75rem', fontWeight: '700' }],
        'title-lg': ['1.5rem', { lineHeight: '2rem', fontWeight: '700' }],
      },
      boxShadow: {
        popover: 'var(--ui-shadow-popover)',
        dialog: 'var(--ui-shadow-dialog)',
        drag: 'var(--ui-shadow-drag)',
      },
      transitionDuration: {
        fast: 'var(--ui-duration-fast)',
        normal: 'var(--ui-duration-normal)',
      },
      zIndex: {
        sticky: 'var(--ui-z-sticky)',
        dock: 'var(--ui-z-dock)',
        dialog: 'var(--ui-z-dialog)',
        dropdown: 'var(--ui-z-dropdown)',
        popover: 'var(--ui-z-popover)',
        'confirm-overlay': 'var(--ui-z-confirm-overlay)',
        toast: 'var(--ui-z-toast)',
      },
    },
  },
  plugins: [],
}
