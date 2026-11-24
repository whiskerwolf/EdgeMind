/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        em: {
          canvas: '#090A0F',
          sidebar: '#0D0E15',
          workspace: '#10121C',
          card: '#141624',
          elevated: '#191C2E',
          overlay: '#1F233A',
          border: {
            hairline: 'rgba(255, 255, 255, 0.06)',
            default: '#1E2235',
            strong: '#2D334F',
            focus: '#38BDF8',
          },
          text: {
            primary: '#F8FAFC',
            secondary: '#CBD5E1',
            muted: '#94A3B8',
            dim: '#64748B',
            disabled: '#475569',
          },
          accent: {
            primary: '#38BDF8',
            hover: '#0284C7',
            subtle: 'rgba(56, 189, 248, 0.10)',
          },
          status: {
            error: '#EF4444',
            warning: '#F59E0B',
            info: '#38BDF8',
            success: '#10B981',
          },
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Geist Mono', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      borderRadius: {
        sm: '4px',
        md: '6px',
        lg: '8px',
      },
    },
  },
  plugins: [],
}
