import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import { ConsentBanner } from "@/components/consent-banner";
import { ToastProvider } from "@/components/ui/toast";
import { BRAND } from "@/lib/brand";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: `${BRAND.name} — Tes photos Vinted, mais en mieux`, template: `%s · ${BRAND.name}` },
  description:
    "Améliore automatiquement tes photos Vinted avec l'IA : nettoyage, cadrage, lumière et couleurs, tout en conservant l'apparence réelle de ton article.",
  applicationName: BRAND.name,
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}>
      <body className="min-h-full">
        <ToastProvider>
          {children}
          <ConsentBanner />
        </ToastProvider>
      </body>
    </html>
  );
}
