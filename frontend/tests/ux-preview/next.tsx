import type { AnchorHTMLAttributes } from "react";

export default function Link({ prefetch: _prefetch, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { prefetch?: unknown }) {
  void _prefetch;
  return <a {...props} />;
}
export const usePathname = () => new URLSearchParams(location.search).get("path") ?? "/admin/speaking-benchmark";
export const useRouter = () => ({ push: (path: string) => { location.search = new URLSearchParams({ path }).toString(); }, replace: (path: string) => { location.search = new URLSearchParams({ path }).toString(); }, refresh: () => undefined });
