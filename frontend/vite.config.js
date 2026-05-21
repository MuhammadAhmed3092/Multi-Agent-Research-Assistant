import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: "0.0.0.0",
  },
  // VITE_API_URL is set as Railway env var after backend deploys
  // Locally it falls back to localhost:8000
})
