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
 * - `app/favicon.ico`: 16 and 32 px for whatever asks for /favicon.ico by name
 *   (bookmarks, feed readers, older browsers), which would otherwise get a 404.
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

// An ICO is a directory of images; each entry here is a PNG, which every reader since Vista takes.
const favicons = await Promise.all(
  [16, 32].map((size) =>
    sharp(Buffer.from(mark), { density: (72 * size) / 32 })
      .resize(size, size)
      .png({ compressionLevel: 9 })
      .toBuffer()
      .then((png) => ({ size, png })),
  ),
);
const header = Buffer.alloc(6 + 16 * favicons.length);
header.writeUInt16LE(0, 0);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(favicons.length, 4);
let offset = header.length;
favicons.forEach(({ size, png }, index) => {
  const entry = 6 + 16 * index;
  header.writeUInt8(size, entry);
  header.writeUInt8(size, entry + 1);
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(png.length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += png.length;
});
await writeFile(new URL("app/favicon.ico", root), Buffer.concat([header, ...favicons.map(({ png }) => png)]));
console.log("app/favicon.ico 16x16, 32x32");
