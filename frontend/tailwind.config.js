/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans Variable"', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono Variable"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      colors: {
        // OpenStock warm near-black neutral palette remapped to slate
        slate: {
          50: '#f4f6f5',
          100: '#e8eae9',
          200: '#cbd0ce',
          300: '#aeb4b1',
          400: '#8a918e',
          500: '#656c69',
          600: '#444a48',
          700: '#2e3331',
          800: '#222625',
          900: '#181b1a',
          950: '#0d0f0e',
        },
        // OpenStock vibrant emerald accent palette remapped to indigo
        indigo: {
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
          950: '#042a1f',
        },
        background: '#0d0f0e',
        surface: '#181b1a',
        border: '#2e3331',
      }
    },
  },
  plugins: [],
}
