import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI-TPM — Enterprise Autonomous Project Manager",
  description: "AI-Powered Technical Project Manager for sprint tracking, architecture audits, risk management, and multi-agent workflow orchestration.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased bg-[#090d16] text-slate-100 min-h-screen">
        {children}
      </body>
    </html>
  );
}
