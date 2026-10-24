/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Фирменные цвета проекта (ТТК Индор-навигация)
        brand: {
          DEFAULT: '#e30613',
          red: '#e30613',
          blue: '#3b82f6',
          dark: '#020617', // slate-950
          card: '#0f172a', // slate-900
        },
        ttk: {
          DEFAULT: '#e30613',
          red: '#e30613',
        },
        accent: {
          DEFAULT: '#3b82f6',
          blue: '#3b82f6',
          red: '#e30613',
        },
        'ttk-red': '#e30613',
        'brand-red': '#e30613',
        'accent-blue': '#3b82f6',
        'accent-red': '#e30613',
        // Фирменные цвета темной темы (фон и карточки)
        slate: {
          900: '#0f172a',
          950: '#020617',
        },
      },
    },
  },
  plugins: [],
}
