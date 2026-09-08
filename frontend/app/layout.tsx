"use client";

import { Inter } from "next/font/google";
import "./globals.css";
import Link from "next/link";
import { usePathname } from "next/navigation";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const pathname = usePathname();

  return (
    <html
      lang="en"
      className={`${inter.variable} h-full antialiased font-sans`}
    >
      <body className="min-h-full flex flex-col text-zinc-900">
        {/* Global Subtle Background Grid & Glows */}
        <div className="fixed inset-0 z-0 pointer-events-none select-none overflow-hidden bg-zinc-50">
          {/* Subtle dot grid pattern */}
          <div className="absolute inset-0 [mask-image:radial-gradient(100%_100%_at_top_center,white,transparent)]">
            <svg
              className="absolute inset-0 h-full w-full fill-zinc-300/35"
              aria-hidden="true"
            >
              <defs>
                <pattern
                  id="global-dot-grid"
                  width={24}
                  height={24}
                  patternUnits="userSpaceOnUse"
                  x="50%"
                  y={-1}
                >
                  <circle cx={1.5} cy={1.5} r={1} />
                </pattern>
              </defs>
              <rect
                width="100%"
                height="100%"
                strokeWidth={0}
                fill="url(#global-dot-grid)"
              />
            </svg>
          </div>

          {/* Ambient Glowing Blobs */}
          <div className="absolute top-0 left-1/4 -translate-x-1/2 -translate-y-1/2 w-[550px] h-[550px] bg-indigo-300/20 rounded-full blur-3xl" />
          <div className="absolute top-1/3 right-1/4 translate-x-1/2 w-[550px] h-[550px] bg-purple-300/20 rounded-full blur-3xl" />
        </div>

        {/* Unified Modern Glassmorphic Header */}
        <header className="sticky top-0 z-40 w-full border-b border-zinc-200/50 bg-white/80 backdrop-blur-md shadow-3xs">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-8">
              <Link href="/dashboard" className="flex items-center gap-2 group">
                <span className="inline-block pe-1 pb-0.5 font-black tracking-tight text-base bg-gradient-to-r from-indigo-600 to-indigo-850 bg-clip-text text-transparent transition-transform duration-200 group-hover:scale-[1.02]">
                  Nexora
                </span>
                <span className="inline-flex items-center rounded bg-indigo-50 px-1.5 py-0.5 text-[9px] font-bold text-indigo-700 uppercase tracking-wider border border-indigo-100/50">
                  Copilot
                </span>
              </Link>
              <nav className="flex items-center gap-4 sm:gap-6 text-xs font-semibold overflow-x-auto no-scrollbar whitespace-nowrap max-w-[calc(100vw-180px)] sm:max-w-none">
                <Link
                  href="/"
                  className={`transition-colors py-1.5 relative ${
                    pathname === "/"
                      ? "text-indigo-600 font-bold"
                      : "text-zinc-500 hover:text-zinc-900"
                  }`}
                >
                  Home
                  {pathname === "/" && (
                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full animate-fade-in" />
                  )}
                </Link>
                <Link
                  href="/dashboard"
                  className={`transition-colors py-1.5 relative ${
                    pathname === "/dashboard"
                      ? "text-indigo-600 font-bold"
                      : "text-zinc-500 hover:text-zinc-900"
                  }`}
                >
                  Dashboard
                  {pathname === "/dashboard" && (
                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full animate-fade-in" />
                  )}
                </Link>
                <Link
                  href="/chat"
                  className={`transition-colors py-1.5 relative ${
                    pathname === "/chat"
                      ? "text-indigo-600 font-bold"
                      : "text-zinc-500 hover:text-zinc-900"
                  }`}
                >
                  AI Copilot
                  {pathname === "/chat" && (
                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full animate-fade-in" />
                  )}
                </Link>
                <Link
                  href="/customers"
                  className={`transition-colors py-1.5 relative ${
                    pathname === "/customers"
                      ? "text-indigo-600 font-bold"
                      : "text-zinc-500 hover:text-zinc-900"
                  }`}
                >
                  Customers
                  {pathname === "/customers" && (
                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full animate-fade-in" />
                  )}
                </Link>
                <Link
                  href="/simulation"
                  className={`transition-colors py-1.5 relative ${
                    pathname === "/simulation"
                      ? "text-indigo-600 font-bold"
                      : "text-zinc-500 hover:text-zinc-900"
                  }`}
                >
                  Simulation
                  {pathname === "/simulation" && (
                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full animate-fade-in" />
                  )}
                </Link>
              </nav>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main
          className={
            pathname === "/simulation"
              ? "flex-1 flex flex-col w-full h-[calc(100vh-3.5rem)] overflow-hidden relative z-10"
              : "flex-1 flex flex-col mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8 relative z-10"
          }
        >
          {children}
        </main>

        {/* Footer */}
        {pathname !== "/simulation" && (
          <footer className="border-t border-zinc-200/50 bg-white py-8 text-center text-3xs font-medium text-zinc-400 relative z-10">
            <div>
              &copy; {new Date().getFullYear()} Nexora AI-Native Campaign CRM.
              Built with next-generation event analytics.
            </div>
          </footer>
        )}
      </body>
    </html>
  );
}
