import { createServer } from "node:net";
import { defineConfig, devices } from "@playwright/test";

/** Ask the OS for a free port so no port number is written down anywhere. */
function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, () => {
      const address = server.address();
      server.close(() => (address && typeof address === "object" ? resolve(address.port) : reject(new Error("no port"))));
    });
  });
}

// The first process to load this file picks the port and exports it, so workers and the web server agree.
process.env.PLAYWRIGHT_WEB_PORT ||= String(await freePort());
const port = process.env.PLAYWRIGHT_WEB_PORT;

// The mocked specs intercept every /v1 request in the browser, so the app is served as a plain production build
// with no API behind it (and therefore no proxy target is needed).
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://localhost:${port}`, trace: "retain-on-failure", reducedMotion: "reduce" },
  webServer: {
    command: `npm run build && npx vite preview --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    { name: "desktop-light", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 }, colorScheme: "light" } },
    { name: "desktop-dark", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 }, colorScheme: "dark" } },
    { name: "phone-light", use: { ...devices["Pixel 7"], colorScheme: "light" } },
    { name: "phone-dark", use: { ...devices["Pixel 7"], colorScheme: "dark" } },
  ],
});
