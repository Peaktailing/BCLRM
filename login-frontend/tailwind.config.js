/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#E1251B",
        "primary-dark": "#c41a12",
        "primary-light": "#ff4d4f",
        "primary-50": "#fff1f0",
        "primary-100": "#ffe7e7",
        "bg-main": "#F5F5F5",
        "bg-sub": "#F8F9FA",
        "bg-surface": "#FFFFFF",
        "bg-sidebar": "#1A1A2E",
        "text-main": "#0F172A",
        "text-sub": "#64748B",
        "text-muted": "#94A3B8",
        "text-tertiary": "#94A3B8",
        "text-inverse": "#FFFFFF",
        "border-light": "#E2E8F0",
        "border-medium": "#CBD5E1",
        "border": "#E2E8F0",
        accent: {
          green: "#00B42A",
          orange: "#FF7D00",
          red: "#F53F3F",
          cyan: "#0FC6C2",
          blue: "#5E71E4",
        },
      },
      fontFamily: {
        sans: ["Noto Sans SC", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
      },
      boxShadow: {
        card: "0 2px 8px rgba(0, 0, 0, 0.06)",
        "card-hover": "0 4px 16px rgba(0, 0, 0, 0.1)",
        primary: "0 4px 12px rgba(225, 37, 27, 0.3)",
        "primary-hover": "0 6px 20px rgba(225, 37, 27, 0.4)",
      },
    },
  },
  plugins: [],
};
