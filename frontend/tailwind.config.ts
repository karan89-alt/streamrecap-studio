import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        studio: {
          950: "#090A0F",
          900: "#0D0F17",
          850: "#131722",
          800: "#1A1F2C",
          700: "#272E3F",
          600: "#38435C",
          500: "#556485",
        },
        brand: {
          accent: "#FF4655", // energetic gaming red/coral
          yellow: "#FFB800", // GTA style vibrant highlight
          cyan: "#00F0FF",   // high-tech live stream indicator
          purple: "#7C3AED", // AI synthesis indicator
        }
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 10px rgba(255, 70, 85, 0.2)' },
          '100%': { boxShadow: '0 0 25px rgba(255, 70, 85, 0.6)' },
        }
      }
    },
  },
  plugins: [],
};
export default config;
