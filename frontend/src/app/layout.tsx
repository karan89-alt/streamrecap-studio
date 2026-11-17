import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "StreamRecap Studio | AI Gaming Video Editor & Hindi Voiceover",
  description: "Turn 4-6 hour long YouTube gaming streams into 15-25 minute edited Movie-Explainer videos with time-synced Hindi commentary.",
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
