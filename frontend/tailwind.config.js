/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Playfair Display"', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        pitch: {
          950: '#05070f',
          900: '#0a0e1a',
          800: '#0f1629',
          700: '#141e35',
          600: '#1a2640',
        },
        gold: {
          400: '#f5c842',
          500: '#e8b800',
          600: '#c49a00',
        },
        ember: {
          400: '#ff6b35',
          500: '#ff5500',
          600: '#e04a00',
        },
      },
      animation: {
        'gradient-shift': 'gradientShift 15s ease infinite',
        'float':          'float 7s ease-in-out infinite',
        'float-slow':     'float 10s ease-in-out infinite',
        'pulse-slow':     'pulse 4s cubic-bezier(0.4,0,0.6,1) infinite',
        'fade-in':        'fadeIn 0.6s ease forwards',
        'slide-up':       'slideUp 0.5s cubic-bezier(0.16,1,0.3,1) forwards',
        'slide-in-right': 'slideInRight 0.4s cubic-bezier(0.16,1,0.3,1) forwards',
        'scale-in':       'scaleIn 0.3s cubic-bezier(0.16,1,0.3,1) forwards',
        'shimmer':        'shimmer 2s linear infinite',
      },
      keyframes: {
        gradientShift: {
          '0%,100%': { 'background-position': '0% 50%' },
          '50%':      { 'background-position': '100% 50%' },
        },
        float:        { '0%,100%': { transform: 'translateY(0px)' },   '50%': { transform: 'translateY(-14px)' } },
        fadeIn:       { from: { opacity: '0' },                         to:   { opacity: '1' } },
        slideUp:      { from: { opacity: '0', transform: 'translateY(32px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        slideInRight: { from: { opacity: '0', transform: 'translateX(24px)' }, to: { opacity: '1', transform: 'translateX(0)' } },
        scaleIn:      { from: { opacity: '0', transform: 'scale(0.95)' },      to: { opacity: '1', transform: 'scale(1)' } },
        shimmer:      { '0%': { 'background-position': '-200% 0' }, '100%': { 'background-position': '200% 0' } },
      },
      backgroundSize: { '300%': '300%' },
      boxShadow: {
        'glow-orange': '0 0 40px rgba(255,107,53,0.25)',
        'glow-gold':   '0 0 40px rgba(245,200,66,0.20)',
        'card':        '0 4px 32px rgba(0,0,0,0.4), 0 1px 0 rgba(255,255,255,0.05)',
        'card-hover':  '0 8px 48px rgba(0,0,0,0.5), 0 1px 0 rgba(255,255,255,0.08)',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
