/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#172033',
        navy: '#1f3a5f',
        paper: '#f7f8fb',
        line: '#e4e8ef',
        accent: '#2f6fed',
      },
      fontFamily: { sans: ['Instrument Sans', 'Inter', 'sans-serif'] },
    },
  },
  plugins: [],
}
