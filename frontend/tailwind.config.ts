import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#FFFFFF",
        panel: "#000000",
        panel2: "#000000",
        ink: "#000000",
        inkSoft: "#FFFFFF",
        electric: "#000000",
        violet: "#000000",
        mint: "#000000",
        coral: "#000000",
        lavender: "#000000",
        sky: "#000000",
      },
      fontFamily: {
        display: ["Sora", "Space Grotesk", "sans-serif"],
        body: ["Manrope", "sans-serif"],
      },
      maxWidth: {
        measure: "38rem",
      },
      backgroundImage: {
        "grid-faint": "none",
      },
      backgroundSize: {
        grid: "48px 48px",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0px) rotate(var(--tilt, 0deg))" },
          "50%": { transform: "translateY(-14px) rotate(var(--tilt, 0deg))" },
        },
        drift: {
          "0%": { transform: "translate(0,0)" },
          "50%": { transform: "translate(12px,-10px)" },
          "100%": { transform: "translate(0,0)" },
        },
      },
      animation: {
        float: "float 7s ease-in-out infinite",
        "float-slow": "float 10s ease-in-out infinite",
        drift: "drift 14s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
