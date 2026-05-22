/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#6366f1', // 对应原来的 Indigo
          foreground: '#ffffff',
        },
      },
    },
  },
  plugins: [],
}
