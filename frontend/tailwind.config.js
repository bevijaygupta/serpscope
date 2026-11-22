/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: '#080b12',
        panel: '#0d121c',
        elevated: '#131a27',
        edge: '#1e293b',
        ink: '#e6edf7',
        muted: '#8494ad',
        accent: '#38bdf8',
        violet: '#8b5cf6',
        success: '#34d399',
        warning: '#fbbf24',
        danger: '#fb7185',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(56,189,248,.18), 0 18px 50px -20px rgba(56,189,248,.35)',
      },
      keyframes: {
        'fade-in': { from: { opacity: '0', transform: 'translateY(6px)' }, to: { opacity: '1', transform: 'none' } },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
      },
      animation: {
        'fade-in': 'fade-in .35s ease-out both',
        shimmer: 'shimmer 1.8s infinite',
      },
    },
  },
  plugins: [],
};
