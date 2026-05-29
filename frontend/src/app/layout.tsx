import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import NavBar from "@/components/NavBar";
import ClientLayout from "@/components/ClientLayout";
import { ThemeProvider } from "@/lib/theme";

const inter = Inter({
  subsets: ["latin", "vietnamese"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "RAG Documents Summary",
  description: "Modern document summarization with AI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" suppressHydrationWarning className="h-full">
      <head>
        <script dangerouslySetInnerHTML={{
          __html: `(function(){try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.classList.add(t);else document.documentElement.classList.add("dark");}catch(e){document.documentElement.classList.add("dark")}})()`,
        }} />
      </head>
      <body
        className={`flex flex-col h-screen w-screen overflow-hidden ${inter.variable} font-sans antialiased bg-primary text-primary selection:bg-primary/20 relative`}
      >
        <div className="fixed inset-0 pointer-events-none -z-10">
          <div className="absolute top-[-5%] left-[5%] w-[35%] h-[35%] bg-emerald-500/10 dark:bg-indigo-500/10 blur-[150px] rounded-full" />
          <div className="absolute bottom-[-5%] right-[5%] w-[30%] h-[30%] bg-emerald-500/8 dark:bg-indigo-500/8 blur-[150px] rounded-full" />
          <div className="absolute top-[40%] left-[50%] -translate-x-1/2 w-[20%] h-[20%] bg-blue-500/6 blur-[120px] rounded-full" />
        </div>

        <ThemeProvider>
          <NavBar />
          <ClientLayout>{children}</ClientLayout>
        </ThemeProvider>
      </body>
    </html>
  );
}
