"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const routes = [
  { href: "/analyze", index: "01", label: "Race analysis" },
  { href: "/engineer", index: "02", label: "Race engineer" },
] as const;

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="site-header">
      <div className="site-header__redline" />
      <nav className="site-nav" aria-label="Main navigation">
        <Link
          href="/"
          className="brand-lockup"
          aria-label="Apex Strategist home"
        >
          <span className="brand-mark" aria-hidden>
            <i />
            <i />
            <i />
          </span>
          <span>
            <strong>APEX</strong>
            <small>STRATEGIST</small>
          </span>
        </Link>
        <div className="site-nav__routes">
          {routes.map((route) => {
            const active = pathname === route.href;
            return (
              <Link
                key={route.href}
                href={route.href}
                aria-current={active ? "page" : undefined}
                className={`nav-route ${active ? "nav-route--active" : ""}`}
              >
                <span>{route.index}</span>
                {route.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
