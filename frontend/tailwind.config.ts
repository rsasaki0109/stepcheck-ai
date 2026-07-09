import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        completed: "#16a34a",
        notdone: "#dc2626",
        unknown: "#d97706",
      },
    },
  },
  plugins: [],
};

export default config;
