"use client";

import {
  Database,
  GitBranch,
  Hexagon,
  LayoutDashboard,
  LogOut,
  Menu,
  ScrollText,
  Search,
  Waypoints,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/graph", label: "Graph", icon: Waypoints },
  { href: "/vectors", label: "Vectors", icon: Search },
  { href: "/entities", label: "Entities", icon: Database },
  { href: "/queries", label: "Queries", icon: ScrollText },
  { href: "/ingestion", label: "Ingestion", icon: GitBranch },
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavContent({ pathname, signOut }: { pathname: string; signOut: boolean }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-4 py-5">
        <Hexagon className="h-5 w-5 text-primary" />
        <span className="text-base font-semibold tracking-tight">opencg</span>
      </div>
      <nav className="flex-1 space-y-1 px-2">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive(pathname, href)
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>
      <div className="flex items-center justify-between border-t px-4 py-3">
        <span className="text-xs text-muted-foreground">Admin</span>
        <div className="flex items-center gap-1">
          {signOut ? (
            <form method="post" action="/api/auth/logout">
              <Button type="submit" variant="ghost" size="icon" aria-label="Sign out" title="Sign out">
                <LogOut className="h-4 w-4" />
              </Button>
            </form>
          ) : null}
          <ThemeToggle />
        </div>
      </div>
    </div>
  );
}

export interface SidebarProps {
  /** Show a sign-out control (the admin access gate is enabled). */
  signOut?: boolean;
}

export function Sidebar({ signOut = false }: SidebarProps) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 border-r bg-card md:block">
        <NavContent pathname={pathname} signOut={signOut} />
      </aside>
      <div className="flex items-center gap-2 border-b bg-card px-4 py-2 md:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open navigation">
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-56 p-0">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <div onClick={() => setOpen(false)}>
              <NavContent pathname={pathname} signOut={signOut} />
            </div>
          </SheetContent>
        </Sheet>
        <span className="text-sm font-semibold">opencg</span>
      </div>
    </>
  );
}
