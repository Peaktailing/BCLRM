/** @type {import('tailwindcss').Config} */

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    container: {
      center: true,
    },
    extend: {
      colors: {
        primary: "#FF6B6B",
        "primary-dark": "#ee5a52",
        "primary-light": "#ff8a8a",
        "primary-50": "#fff5f5",
        "primary-100": "#ffe8e8",
        "bg-main": "#FFFFFF",
        "bg-sub": "#F8F9FA",
        "bg-card": "#FFFFFF",
        "text-main": "#262730",
        "text-sub": "#6c757d",
        "text-muted": "#adb5bd",
        "border-light": "#e9ecef",
        "border-medium": "#dee2e6",
      },
      fontFamily: {
        sans: ["Noto Sans SC", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
      },
      boxShadow: {
        card: "0 2px 8px rgba(0, 0, 0, 0.06)",
        "card-hover": "0 4px 16px rgba(0, 0, 0, 0.1)",
        primary: "0 4px 12px rgba(255, 107, 107, 0.3)",
        "primary-hover": "0 6px 20px rgba(255, 107, 107, 0.4)",
      },
      animation: {
        "fade-in": "fadeIn 0.4s ease-out",
        "slide-up": "slideUp 0.5s ease-out",
        "blob-drift": "blobDrift 25s ease-in-out infinite",
        "blob-drift-slow": "blobDrift 35s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        blobDrift: {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "33%": { transform: "translate(30px, -30px) scale(1.1)" },
          "66%": { transform: "translate(-20px, 20px) scale(0.95)" },
        },
      },
    },
  },
  plugins: [],
};
