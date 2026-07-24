/**
 * 文件功能：将 Editor 语义化 Design Token 映射为 Tailwind 工具类。
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: 'rgb(var(--ui-canvas) / <alpha-value>)',
        surface: {
          DEFAULT: 'rgb(var(--ui-surface) / <alpha-value>)',
          raised: 'rgb(var(--ui-surface-raised) / <alpha-value>)',
          muted: 'rgb(var(--ui-surface-muted) / <alpha-value>)',
          hover: 'rgb(var(--ui-surface-hover) / <alpha-value>)',
          selected: 'rgb(var(--ui-surface-selected) / <alpha-value>)',
        },
        text: {
          DEFAULT: 'rgb(var(--ui-text) / <alpha-value>)',
          secondary: 'rgb(var(--ui-text-secondary) / <alpha-value>)',
          muted: 'rgb(var(--ui-text-muted) / <alpha-value>)',
          disabled: 'rgb(var(--ui-text-disabled) / <alpha-value>)',
          inverse: 'rgb(var(--ui-text-inverse) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--ui-border) / <alpha-value>)',
          strong: 'rgb(var(--ui-border-strong) / <alpha-value>)',
          focus: 'rgb(var(--ui-border-focus) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--ui-accent) / <alpha-value>)',
          hover: 'rgb(var(--ui-accent-hover) / <alpha-value>)',
          muted: 'rgb(var(--ui-accent-muted) / <alpha-value>)',
        },
        danger: {
          DEFAULT: 'rgb(var(--ui-danger) / <alpha-value>)',
          muted: 'rgb(var(--ui-danger-muted) / <alpha-value>)',
        },
        warning: {
          DEFAULT: 'rgb(var(--ui-warning) / <alpha-value>)',
          muted: 'rgb(var(--ui-warning-muted) / <alpha-value>)',
        },
        success: {
          DEFAULT: 'rgb(var(--ui-success) / <alpha-value>)',
          muted: 'rgb(var(--ui-success-muted) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'rgb(var(--ui-info) / <alpha-value>)',
          muted: 'rgb(var(--ui-info-muted) / <alpha-value>)',
        },
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
        dropdown: 'var(--ui-z-dropdown)',
        popover: 'var(--ui-z-popover)',
        dialog: 'var(--ui-z-dialog)',
        toast: 'var(--ui-z-toast)',
      },
    },
  },
  plugins: [],
}
