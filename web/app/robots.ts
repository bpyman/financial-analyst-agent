import type { MetadataRoute } from "next";

/** The window is for crawlers to read; the API behind it is not (every call spends the visitor's quota). */
export default function robots(): MetadataRoute.Robots {
  return { rules: { userAgent: "*", allow: "/", disallow: "/api/" } };
}
