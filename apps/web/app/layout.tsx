import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Orca Research",
  description: "Orca Research — 检索式研究助手(Phase 1B)",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
