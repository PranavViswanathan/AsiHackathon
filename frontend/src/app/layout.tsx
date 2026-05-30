import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AirFlow - Airspace Congestion Dashboard",
  description: "Visualize flights, fuel cost, and sectors over a US map",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-white h-full">{children}</body>
    </html>
  );
}
