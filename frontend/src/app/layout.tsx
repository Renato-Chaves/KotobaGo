import type { Metadata } from "next";
import { Noto_Sans_JP } from "next/font/google";
import "./globals.css";

const notoSansJP = Noto_Sans_JP({
  variable: "--font-noto-sans-jp",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

export const metadata: Metadata = {
  title: "KotobaGo",
  description:
    "AI-powered Japanese language learning through comprehensible input",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${notoSansJP.variable} dark`}>
      <body className="min-h-screen bg-zinc-950 text-zinc-100 font-[family-name:var(--font-noto-sans-jp)] antialiased">
        {children}
      </body>
    </html>
  );
}
