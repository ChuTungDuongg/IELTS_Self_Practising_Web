import { useId } from "react";

type AppLogoVariant = "primary" | "monochrome" | "icon";

type AppLogoProps = {
  variant?: AppLogoVariant;
  className?: string;
  title?: string;
};

// One rounded, folded ribbon, repeated around a shared negative-space target.
const ribbonPath = "M30 5.5C32.1 4.3 34.5 5.8 34.5 8.2V16.5C34.5 18.4 36.1 20 38 20H44.5C46.4 20 47.1 22.5 45.5 23.5L43 25C42 25.6 40.9 26 39.7 26H31C27.4 26 24.5 23.1 24.5 19.5V11.7C24.5 10.5 25.1 9.4 26.1 8.8Z";

export function AppLogo({ variant = "primary", className = "", title }: AppLogoProps) {
  const gradientId = `bandpilot-ribbon-${useId()}`;
  const monochrome = variant === "monochrome";
  const accessibility = title
    ? { role: "img", "aria-label": title }
    : { "aria-hidden": true };

  return (
    <svg
      viewBox="0 0 64 64"
      className={`app-logo app-logo-${variant} ${className}`.trim()}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      {...accessibility}
    >
      {title ? <title>{title}</title> : null}
      {!monochrome ? (
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
            <stop stopColor="#4F46E5" />
            <stop offset=".5" stopColor="#3B82F6" />
            <stop offset="1" stopColor="#22B8CF" />
          </linearGradient>
        </defs>
      ) : null}
      <g fill={monochrome ? "currentColor" : `url(#${gradientId})`}>
        {[0, 90, 180, 270].map(rotation => (
          <path key={rotation} d={ribbonPath} transform={`rotate(${rotation} 32 32)`} />
        ))}
      </g>
    </svg>
  );
}
