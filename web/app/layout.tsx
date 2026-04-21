import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import ThemeScript from "@/components/ThemeScript";
import { AppShellProvider } from "@/context/AppShellContext";
import { I18nClientBridge } from "@/i18n/I18nClientBridge";

const fontSans = localFont({
  src: [
    { path: "../public/fonts/LDIbaomQNQcsA88c7O9yZ4KMCoOg4IA6-91aHEjcWuA_KU7NSg.ttf", weight: "200", style: "normal" },
    { path: "../public/fonts/LDIbaomQNQcsA88c7O9yZ4KMCoOg4IA6-91aHEjcWuA_907NSg.ttf", weight: "300", style: "normal" },
    { path: "../public/fonts/LDIbaomQNQcsA88c7O9yZ4KMCoOg4IA6-91aHEjcWuA_qU7NSg.ttf", weight: "400", style: "normal" },
    { path: "../public/fonts/LDIbaomQNQcsA88c7O9yZ4KMCoOg4IA6-91aHEjcWuA_m07NSg.ttf", weight: "500", style: "normal" },
    { path: "../public/fonts/LDIbaomQNQcsA88c7O9yZ4KMCoOg4IA6-91aHEjcWuA_d0nNSg.ttf", weight: "600", style: "normal" },
    { path: "../public/fonts/LDIbaomQNQcsA88c7O9yZ4KMCoOg4IA6-91aHEjcWuA_TknNSg.ttf", weight: "700", style: "normal" },
    { path: "../public/fonts/LDIbaomQNQcsA88c7O9yZ4KMCoOg4IA6-91aHEjcWuA_KUnNSg.ttf", weight: "800", style: "normal" },
  ],
  display: "swap",
  variable: "--font-sans",
});

const fontSerif = localFont({
  src: [
    { path: "../public/fonts/0QI6MX1D_JOuGQbT0gvTJPa787weuyJG.ttf", weight: "400", style: "normal" },
    { path: "../public/fonts/0QI6MX1D_JOuGQbT0gvTJPa787wsuyJG.ttf", weight: "500", style: "normal" },
    { path: "../public/fonts/0QI6MX1D_JOuGQbT0gvTJPa787zAvCJG.ttf", weight: "600", style: "normal" },
    { path: "../public/fonts/0QI6MX1D_JOuGQbT0gvTJPa787z5vCJG.ttf", weight: "700", style: "normal" },
  ],
  display: "swap",
  variable: "--font-serif",
});

export const metadata: Metadata = {
  title: "DeepTutor",
  description: "Agent-native intelligent learning companion",
  icons: {
    icon: [
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      data-scroll-behavior="smooth"
      className={`${fontSans.variable} ${fontSerif.variable}`}
    >
      <head>
        <ThemeScript />
      </head>
      <body className="font-sans bg-[var(--background)] text-[var(--foreground)]">
        <AppShellProvider>
          <I18nClientBridge>
            {children}
          </I18nClientBridge>
        </AppShellProvider>
      </body>
    </html>
  );
}
