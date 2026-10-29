import type { SVGProps } from "react";

const paths = {
  email: "m3 6 9 7 9-7M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z",
  lock: "M7 10V7a5 5 0 0 1 10 0v3M6 10h12a2 2 0 0 1 2 2v8H4v-8a2 2 0 0 1 2-2Zm6 4v3",
  person: "M20 21v-2a7 7 0 0 0-14 0v2M17 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Zm13 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
  eyeOff: "m3 3 18 18M10.6 5.1 12 5c6.5 0 10 7 10 7a22 22 0 0 1-3.2 4.2M6.2 6.2A23 23 0 0 0 2 12s3.5 7 10 7c2.1 0 4-.7 5.5-1.7M10 10a3 3 0 0 0 4 4",
  arrow: "M4 12h16m-6-6 6 6-6 6",
  progress: "M4 19h16M6 14l4-4 4 2 5-7m-5 0h5v5",
  target: "M21 12a9 9 0 1 1-9-9m5 1-5 8m0-5a5 5 0 1 0 5 5",
  clock: "M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  flag: "M5 21V4m0 0c5-4 9 4 14 0v10c-5 4-9-4-14 0",
  reading: "M12 5v15M3 4c4-1 6 0 9 2 3-2 5-3 9-2v15c-4-1-6 0-9 2-3-2-5-3-9-2V4Z",
  listening: "M4 14v-3a8 8 0 0 1 16 0v3M4 12h2v8H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2Zm16 0h-2v8h2a2 2 0 0 0 2-2v-4a2 2 0 0 0-2-2Z",
  writing: "m14 5 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14l-1 7 1-1Z",
  speaking: "M8 10V6a4 4 0 0 1 8 0v4a4 4 0 0 1-8 0Zm-3 0a7 7 0 0 0 14 0m-7 7v4m-4 0h8",
} as const;

export type AuthIconName = keyof typeof paths;

export function AuthIcon({ name, ...props }: SVGProps<SVGSVGElement> & { name: AuthIconName }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}><path d={paths[name]} /></svg>;
}

export function GoogleIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36Z" />
    <path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.05.96-3.38.96-2.6 0-4.8-1.76-5.59-4.12H3.07v2.59A10 10 0 0 0 12 22Z" />
    <path fill="#FBBC05" d="M6.41 13.92a6 6 0 0 1 0-3.84V7.49H3.07a10 10 0 0 0 0 9.02l3.34-2.59Z" />
    <path fill="#EA4335" d="M12 5.96c1.47 0 2.79.5 3.82 1.49l2.87-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.93 5.49l3.34 2.59A6 6 0 0 1 12 5.96Z" />
  </svg>;
}
