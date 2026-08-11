import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const frontendDirectory = path.dirname(fileURLToPath(import.meta.url));
const subtitlePath = path.resolve(frontendDirectory, "../data/subtitles/bilingual.srt");
const backendTarget =
  process.env.VIDEOMIND_BACKEND_URL || "http://127.0.0.1:8000";

function subtitleDownloadMiddleware(middlewares) {
  middlewares.use("/downloads/bilingual.srt", (request, response, next) => {
    if (request.method !== "GET" && request.method !== "HEAD") {
      next();
      return;
    }

    fs.stat(subtitlePath, (error, stats) => {
      if (error || !stats.isFile()) {
        response.statusCode = 404;
        response.setHeader("Content-Type", "application/json; charset=utf-8");
        response.end(
          JSON.stringify({ detail: "bilingual.srt has not been generated yet." }),
        );
        return;
      }

      response.statusCode = 200;
      response.setHeader("Content-Type", "application/x-subrip; charset=utf-8");
      response.setHeader(
        "Content-Disposition",
        'attachment; filename="bilingual.srt"',
      );
      response.setHeader("Content-Length", String(stats.size));
      response.setHeader("Cache-Control", "no-store");

      if (request.method === "HEAD") {
        response.end();
        return;
      }

      const stream = fs.createReadStream(subtitlePath);
      stream.on("error", next);
      stream.pipe(response);
    });
  });
}

function subtitleDownloadPlugin() {
  return {
    name: "videomind-subtitle-download",
    configureServer(server) {
      subtitleDownloadMiddleware(server.middlewares);
    },
    configurePreviewServer(server) {
      subtitleDownloadMiddleware(server.middlewares);
    },
  };
}

const apiProxy = {
  "/api": {
    target: backendTarget,
    changeOrigin: true,
    rewrite: (requestPath) => requestPath.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  plugins: [react(), subtitleDownloadPlugin()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: apiProxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    proxy: apiProxy,
  },
});