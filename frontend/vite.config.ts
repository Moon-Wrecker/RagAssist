import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const root = path.dirname(fileURLToPath(import.meta.url));

// The API is same-origin in every environment so the SameSite=Strict refresh cookie is always sent.
// In dev, Vite proxies /v1 to the origin named in the environment; there is no built-in default.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, root, "");
  const target = env.API_PROXY_TARGET;
  const isDev = mode === "development";
  if (isDev && !target) {
    throw new Error("API_PROXY_TARGET is not set. Copy frontend/.env.example to frontend/.env and fill it in.");
  }
  const proxy = target
    ? { "/v1": { target, changeOrigin: false, xfwd: true }, "/healthz": { target, changeOrigin: false } }
    : undefined;
  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { "@": path.resolve(root, "src") } },
    server: { proxy },
    preview: { proxy },
    build: { sourcemap: false, target: "es2022" },
  };
});
