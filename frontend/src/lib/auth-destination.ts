const AUTH_ROUTES = ["/login", "/register", "/session/restore"];

export function safeAuthDestination(next: string | null | undefined): string {
  if (!next?.startsWith("/") || next.startsWith("//") || next.includes("\\")) return "/";
  // Browsers strip control characters and normalize slashes/dot segments in URLs.
  if ([...next].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) return "/";
  try {
    const base = "https://auth-destination.invalid";
    const destination = new URL(next, base);
    const pathname = decodeURIComponent(destination.pathname);
    if (destination.origin !== base || pathname.includes("\\")) return "/";
    // Returning to another auth entry point could repeat the restore/login cycle.
    if (AUTH_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`))) return "/";
    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return "/";
  }
}

export function authRedirectPath(route: "/login" | "/session/restore", next: string | null | undefined): string {
  return `${route}?${new URLSearchParams({ next: safeAuthDestination(next) })}`;
}
