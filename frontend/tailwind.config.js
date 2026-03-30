/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
        display: ["Outfit", "system-ui", "sans-serif"],
      },
      colors: {
        ink: { 950: "#0c0f14", 800: "#1a2230", 600: "#3d4f66" },
        mist: "#e8edf5",
        accent: "#0d9488",
        warn: "#c2410c",
      },
    },
  },
  plugins: [],
};
