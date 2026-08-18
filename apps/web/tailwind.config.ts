import type { Config } from "tailwindcss";

export default {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        asphalt: "#08090b",
        panel: "#111318",
        line: "#282c35",
        signal: "#ff4d2e",
        mist: "#a7acb8",
      },
      fontFamily: { sans: ["var(--font-inter)", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
