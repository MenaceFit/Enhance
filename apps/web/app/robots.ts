import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  // User areas, the API and photo files are never indexed.
  return { rules: [{ userAgent: "*", allow: "/", disallow: ["/app", "/admin", "/api", "/login", "/signup"] }] };
}
