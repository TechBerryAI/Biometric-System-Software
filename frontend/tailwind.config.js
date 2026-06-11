/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"],
        display: ["Inter", "system-ui", "Segoe UI", "sans-serif"],
      },
      fontSize: {
        "display-xl": ["2.25rem", { lineHeight: "1.15", letterSpacing: "-0.03em", fontWeight: "700" }],
        "display-lg": ["1.5rem", { lineHeight: "1.25", letterSpacing: "-0.02em", fontWeight: "600" }],
      },
      colors: {
        surface: {
          DEFAULT: "#F8FAFC",
          card: "#FFFFFF",
        },
        ink: {
          DEFAULT: "#0F172A",
          muted: "#64748B",
          subtle: "#94A3B8",
        },
        line: "#E2E8F0",
        primary: {
          DEFAULT: "#4F46E5",
          hover: "#4338CA",
          soft: "#EEF2FF",
        },
        accent: {
          DEFAULT: "#10B981",
          soft: "#ECFDF5",
        },
        violet: {
          soft: "#F5F3FF",
          DEFAULT: "#7C3AED",
        },
        status: {
          present: "#059669",
          "present-soft": "#D1FAE5",
          late: "#CA8A04",
          "late-soft": "#FEF9C3",
          absent: "#DC2626",
          "absent-soft": "#FEE2E2",
        },
        warn: "#C2410C",
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 24px rgba(15, 23, 42, 0.06)",
        "card-hover":
          "0 2px 4px rgba(15, 23, 42, 0.04), 0 12px 32px rgba(15, 23, 42, 0.08)",
        nav: "0 1px 0 rgba(15, 23, 42, 0.06)",
        inset: "inset 0 1px 0 rgba(255, 255, 255, 0.6)",
      },
      borderRadius: {
        xl: "12px",
        "2xl": "16px",
      },
      transitionDuration: {
        DEFAULT: "200ms",
      },
      cursor: {
        DEFAULT: 'url("/cursors/arrow.svg") 2 2, default',
        pointer: 'url("/cursors/hand.svg") 10 4, pointer',
        text: 'url("/cursors/text.svg") 8 10, text',
      },
    },
  },
  plugins: [],
};
