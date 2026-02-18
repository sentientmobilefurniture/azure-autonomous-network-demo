/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Segoe UI Variable"', '"Segoe UI"', 'system-ui', 'sans-serif'],
      },
      colors: {
        brand: {
          DEFAULT: '#117865',
          hover: '#0E6658',
          light: '#1A9C85',
          subtle: 'rgba(17, 120, 101, 0.08)',
        },
        neutral: {
          bg1: '#FFFFFF',
          bg2: '#FAF9F8',
          bg3: '#F3F2F1',
          bg4: '#EDEBE9',
          bg5: '#E1DFDD',
          bg6: '#D2D0CE',
        },
        text: {
          primary: '#242424',
          secondary: '#616161',
          muted: '#A19F9D',
          tertiary: '#C8C6C4',
        },
        border: {
          subtle: '#F0F0F0',
          DEFAULT: '#E0E0E0',
          strong: '#D1D1D1',
        },
        status: {
          success: '#107C10',
          warning: '#F7630C',
          error: '#A4262C',
          info: '#0078D4',
        },
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
};
