const paths = {
  orbit: "M20 12c0 2.2-3.6 4-8 4s-8-1.8-8-4 3.6-4 8-4 8 1.8 8 4ZM16 5.1c1.9 1.1 1.7 5.2-.5 9s-5.7 6-7.5 4.8-1.7-5.2.5-9S14.1 4 16 5.1Zm0 13.8c-1.9 1.1-5.2-1-7.5-4.8S6.1 6.2 8 5.1s5.2 1 7.5 4.8 2.4 7.9.5 9ZM12 12h.01",
  pause: "M8 5v14M16 5v14",
  play: "m9 5 10 7-10 7V5Z",
  scatter: "M20 10a8 8 0 0 0-14-3L3 10m0-6v6h6m-5 4a8 8 0 0 0 14 3l3-3m0 6v-6h-6",
  info: "M12 11v6m0-10h.01m9 5a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  phone: "m6 3 3 5-2 2a15 15 0 0 0 7 7l2-2 5 3c0 2-2 4-4 3A23 23 0 0 1 3 7c-1-2 1-4 3-4Z",
  arrow: "M6 18 18 6M6 6h12v12",
} as const;

/** Small decorative marks for the homepage footer; brand SVGs stay in FooterContacts. */
export function FooterIcon({ name }: { name: keyof typeof paths }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={paths[name]} /></svg>;
}
