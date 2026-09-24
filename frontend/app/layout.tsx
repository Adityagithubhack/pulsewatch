import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PulseWatch",
  description: "Cloud uptime and incident monitoring",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

