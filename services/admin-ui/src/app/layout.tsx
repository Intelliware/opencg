import { connection } from "next/server";
import type { ReactNode } from "react";
import "./globals.css";

import { Sidebar } from "@/components/Sidebar";
import { ThemeProvider } from "@/components/ThemeProvider";
import { UnauthenticatedBanner } from "@/components/UnauthenticatedBanner";
import { Toaster } from "@/components/ui/sonner";
import { authMode } from "@/lib/auth/config";
import { currentSession } from "@/lib/auth/request";

export const metadata = {
  title: "openCG — Admin",
  description: "Inspect queries, audits, and provider health.",
  icons: { icon: "/opencg-logo.png" },
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  // The auth mode is a runtime setting: never bake it into a prerendered page.
  await connection();
  const open = authMode() === "none";
  const session = open ? null : await currentSession();
  // Only display fields cross to the client; tokens stay on the server.
  const user = session ? { principal: session.principal, roles: session.roles } : null;
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <Sidebar user={user} />
          <main className="mx-auto max-w-6xl px-6 py-6 md:ml-56">
            {open ? <UnauthenticatedBanner /> : null}
            {children}
          </main>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
