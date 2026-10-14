import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "미국 주식 스크리너",
  description: "기존 Python 스크리너의 매수 및 관심 후보와 실행 상태",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
