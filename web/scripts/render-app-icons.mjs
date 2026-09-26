/**
 * Renders the install icons from the one brand mark, `app/icon.svg`, so the browser
 * tab, the installed desktop app, and the home-screen icon all show the same logo.
 * Run it after changing the mark: `node scripts/render-app-icons.mjs`.
 *
 * - `public/icons/icon-{192,512}.png`: the mark as drawn, rounded corners and all,
 *   for Chrome and Edge's installed-app icon (`app/manifest.ts`).
 * - `public/icons/maskable-512.png` and `app/apple-icon.png`: the same mark with
 *   square corners, because Android and iOS cut their own shape out of it. The trend
 *   line already sits inside the maskable safe zone (the centre 80% circle).
 */
import { readFile, writeFile } from "node:fs/promises";
import sharp from "sharp";

const root = new URL("../", import.meta.url);
const mark = await readFile(new URL("app/icon.svg", root), "utf8");
const square = mark.replace(/ rx="[^"]*"/, "");

const outputs = [
  { svg: mark, size: 192, path: "public/icons/icon-192.png" },
  { svg: mark, size: 512, path: "public/icons/icon-512.png" },
  { svg: square, size: 512, path: "public/icons/maskable-512.png" },
  { svg: square, size: 180, path: "app/apple-icon.png" },
];

for (const { svg, size, path } of outputs) {
  const png = await sharp(Buffer.from(svg), { density: (72 * size) / 32 })
    .resize(size, size)
    .png({ compressionLevel: 9 })
    .toBuffer();
  await writeFile(new URL(path, root), png);
  console.log(`${path} ${size}x${size}`);
}
