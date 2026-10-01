import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import { ThemeProvider } from "next-themes";
import { THEME_GUARD_SCRIPT } from "@/lib/theme-guard";
import "./globals.css";

const TITLE = "Onfile — Financial research from SEC filings";
const DESCRIPTION =
  "Explore company financials, straight from SEC filings. Every number links to the filing it came from.";

// The link preview on LinkedIn, X and Slack: the social card that
// scripts/capture-portfolio.ts writes to public/.
const SHARE_IMAGE = {
  url: "/social-preview.png",
  width: 1280,
  height: 640,
  alt: "Onfile: ask about a company, get the number and the filing behind it. Eli Lilly's quarterly revenue overtaking Pfizer's, from their SEC filings.",
};

export const metadata: Metadata = {
  // Shared links resolve their preview image against the public demo.
  metadataBase: new URL("https://onfile-analyst.vercel.app"),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    siteName: "Onfile",
    type: "website",
    url: "/",
    images: [SHARE_IMAGE],
  },
  twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION, images: [SHARE_IMAGE] },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f6f4" },
    { media: "(prefers-color-scheme: dark)", color: "#07080a" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_GUARD_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
