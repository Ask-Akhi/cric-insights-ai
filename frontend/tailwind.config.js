/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        pitch: {
          900: '#0a0e1a',
          800: '#0f1629',
          700: '#141e35',
          600: '#1a2640',
        },
      },
      animation: {
        'gradient-x':  'gradient-x 8s ease infinite',
        'float':       'float 6s ease-in-out infinite',
        'pulse-slow':  'pulse 4s cubic-bezier(0.4,0,0.6,1) infinite',
        'fade-in':     'fadeIn 0.5s ease forwards',
        'slide-up':    'slideUp 0.4s ease forwards',
      },
      keyframes: {
        'gradient-x': {
          '0%,100%': { 'background-position': '0% 50%' },
          '50%':      { 'background-position': '100% 50%' },
        },
        float:   { '0%,100%': { transform: 'translateY(0px)' },    '50%': { transform: 'translateY(-12px)' } },
        fadeIn:  { from: { opacity: '0' },                          to:   { opacity: '1' } },
        slideUp: { from: { opacity: '0', transform: 'translateY(24px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
