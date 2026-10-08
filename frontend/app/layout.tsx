import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "StepCheck AI",
  description: "動画から作業フローを検出し、根拠フレームを確認できます。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
