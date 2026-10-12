import type { Metadata } from "next";
import { Geist, Geist_Mono, Lato } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
// Same typeface as the exported PDF, so the on-screen preview matches the download.
const lato = Lato({ variable: "--font-resume", subsets: ["latin"], weight: ["400", "700"], style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: "Resume Customizer — tailor your resume to any job",
  description: "Paste a job description, upload your resume, and get an AI-tailored, ATS-friendly version in seconds.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} ${lato.variable} font-sans antialiased`}>{children}</body>
    </html>
  );
}
