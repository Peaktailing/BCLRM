/** @type {import('tailwindcss').Config} */

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    container: {
      center: true,
    },
    extend: {
      colors: {
        "lab-bg": "#0a0e1a",
        "lab-card": "rgba(15,23,42,0.6)",
        "lab-cyan": "#00d4ff",
        "lab-teal": "#14b8a6",
        "lab-amber": "#f59e0b",
        "lab-text": "#e2e8f0",
        "lab-muted": "#64748b",
        "lab-border": "rgba(0,212,255,0.2)",
      },
      fontFamily: {
        display: ["Orbitron", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      animation: {
        "molecule-rotate": "rotate 30s linear infinite",
        "molecule-float": "moleculeFloat 8s ease-in-out infinite",
        "glow-pulse": "glowPulse 3s ease-in-out infinite",
        "particle-drift": "particleDrift 20s linear infinite",
        "spin-slow": "spin 1.5s linear infinite",
      },
      keyframes: {
        moleculeFloat: {
          "0%, 100%": { transform: "translateY(0px) rotate(0deg)" },
          "50%": { transform: "translateY(-20px) rotate(180deg)" },
        },
        glowPulse: {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "0.8" },
        },
        particleDrift: {
          "0%": { transform: "translate(0, 0)" },
          "100%": { transform: "translate(100px, -100px)" },
        },
      },
    },
  },
  plugins: [],
};
