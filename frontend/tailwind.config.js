/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // A muted "network-ops" palette; accessible contrast on dark bg.
        ink: {
          950: "#0b0f17",
          900: "#111827",
          800: "#1f2937",
          700: "#374151",
          600: "#4b5563",
          400: "#9ca3af",
          200: "#e5e7eb",
        },
        accent: {
          DEFAULT: "#3b82f6",
          up: "#22c55e",
          down: "#f59e0b",
          warn: "#ef4444",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
