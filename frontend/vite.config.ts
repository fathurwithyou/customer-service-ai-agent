import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Builds straight into the package FastAPI serves, so there is one artefact and no copy step.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/tokokita/api/static", emptyOutDir: true },
  server: { proxy: { "/chat": "http://localhost:8000", "/health": "http://localhost:8000" } },
});
