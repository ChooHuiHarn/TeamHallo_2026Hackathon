import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server on http://localhost:5173 (the origin the backend allows via CORS).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: true },
  preview: { port: 4173 },
});
