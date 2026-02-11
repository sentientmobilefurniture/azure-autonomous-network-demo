/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Segoe UI', 'system-ui', 'sans-serif'],
      },
      colors: {
        brand: {
          DEFAULT: '#8251EE',
          hover: '#9366F5',
          light: '#A37EF5',
          subtle: 'rgba(130, 81, 238, 0.15)',
        },
        neutral: {
          bg1: 'hsl(240, 6%, 10%)',
          bg2: 'hsl(240, 5%, 12%)',
          bg3: 'hsl(240, 5%, 14%)',
          bg4: 'hsl(240, 4%, 18%)',
          bg5: 'hsl(240, 4%, 22%)',
          bg6: 'hsl(240, 4%, 26%)',
        },
        text: {
          primary: '#FFFFFF',
          secondary: '#A1A1AA',
          muted: '#71717A',
        },
        border: {
          subtle: 'hsla(0, 0%, 100%, 0.08)',
          DEFAULT: 'hsla(0, 0%, 100%, 0.12)',
          strong: 'hsla(0, 0%, 100%, 0.20)',
        },
        status: {
          success: '#10B981',
          warning: '#F59E0B',
          error: '#EF4444',
          info: '#3B82F6',
        },
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
};
