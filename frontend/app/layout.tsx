import type { Metadata } from "next";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Wearable Stress Research",
  description: "Stress Detection in Students Using Wearable Data - research prototype",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <Sidebar />
        <main className="px-4 py-6 sm:px-6 lg:ml-60 lg:px-10 lg:py-8">
          <div className="mx-auto max-w-7xl">{children}</div>
        </main>
      </body>
    </html>
  );
}
