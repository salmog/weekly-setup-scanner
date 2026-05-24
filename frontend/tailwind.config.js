/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#09090b",
        surface: "#18181b",
        border: "#27272a",
        primary: "#fafafa",
        muted: "#a1a1aa",
        success: "#10b981",
        danger: "#ef4444",
        warning: "#f59e0b"
      }
    },
  },
  plugins: [],
}
