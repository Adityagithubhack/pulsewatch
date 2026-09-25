import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PulseWatch | Observability Console",
  description: "Uptime, latency, SLO, and incident intelligence for modern services",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
