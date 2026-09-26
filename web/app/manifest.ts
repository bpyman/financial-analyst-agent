import type { MetadataRoute } from "next";

/**
 * Makes the window installable from Chrome and Edge ("Install page as app") with the
 * project's own mark. The PNGs are rendered from `app/icon.svg` by
 * `scripts/render-app-icons.mjs`; the colours are the dark theme's page background.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Financial analyst agent",
    short_name: "Analyst",
    description:
      "Evidence-first financial research: SEC 10-Q facts, constrained planning, numbers the model cannot rewrite.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#07080a",
    theme_color: "#07080a",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
