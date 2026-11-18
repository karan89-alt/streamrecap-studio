import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "StreamRecap Studio | Full HD Gaming Recap Editor",
  description: "Convert long YouTube gaming streams into edited 1080p Full HD recaps with viral captions and time-synced Hindi script.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#090A0F] text-slate-100 antialiased selection:bg-[#FF4655] selection:text-white">
        {children}
      </body>
    </html>
  );
}
