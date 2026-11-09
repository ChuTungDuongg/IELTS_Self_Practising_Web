import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

const local = (path: string) => fileURLToPath(new URL(path, import.meta.url));
export default defineConfig({
  root: local("../.."),
  define: { "process.env.NEXT_PUBLIC_API_BASE_URL": JSON.stringify("/api/v1") },
  resolve: { alias: [
    { find: "next/link", replacement: local("./next.tsx") },
    { find: "next/navigation", replacement: local("./next.tsx") },
    { find: "@/features/auth/auth-provider", replacement: local("./auth.ts") },
    { find: "@", replacement: local("../../src") },
  ] },
  oxc: { jsx: { runtime: "automatic" } },
  plugins: [{ name: "synthetic-audio", configureServer(server) {
    // Sixty seconds of generated silence; no private media is used by this preview.
    const wav = Buffer.alloc(44 + 60 * 8000 * 2);
    wav.write("RIFF"); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8);
    wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
    wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34);
    wav.write("data", 36); wav.writeUInt32LE(wav.length - 44, 40);
    server.middlewares.use((request, response, next) => {
      if (!request.url?.split("?")[0].endsWith("/audio")) return next();
      response.setHeader("Content-Type", "audio/wav");
      response.setHeader("Accept-Ranges", "bytes");
      const range = request.headers.range?.match(/bytes=(\d+)-(\d*)/);
      const start = range ? Number(range[1]) : 0;
      const end = range?.[2] ? Math.min(Number(range[2]), wav.length - 1) : wav.length - 1;
      if (range) { response.statusCode = 206; response.setHeader("Content-Range", `bytes ${start}-${end}/${wav.length}`); }
      response.end(wav.subarray(start, end + 1));
    });
  } }],
  server: { host: "127.0.0.1", port: 3107 },
});
