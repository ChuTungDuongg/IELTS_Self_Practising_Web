type AppLogoVariant = "primary" | "monochrome" | "icon";

type AppLogoProps = {
  variant?: AppLogoVariant;
  className?: string;
  title?: string;
};

export function AppLogo({
  variant = "primary",
  className = "",
  title,
}: AppLogoProps) {
  const accessibility = title
    ? { role: "img", "aria-label": title }
    : { "aria-hidden": true };

  if (variant === "monochrome") {
    return (
      <svg
        viewBox="0 0 64 64"
        className={`app-logo app-logo-monochrome ${className}`.trim()}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        {...accessibility}
      >
        <path d="M7.5 37.5C10.7 24.2 28.3 13.9 45.1 17.2c9.2 1.8 14.1 7 11.4 13.1" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round" />
        <circle cx="32" cy="32" r="17.5" stroke="currentColor" strokeWidth="4.5" />
        <path d="M17.2 24.3c8.2 4.2 21.4 4.6 29.8-.6M14.8 32.2c9.1 4.2 24.4 4.7 34.2-.9M17.4 40c8.1 3.5 20.3 3.8 28.3-.8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        <path d="M56.5 30.3c-3.5 13.2-21 22-37.8 18.3C9.8 46.7 5 41.7 7.5 37.5" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round" />
      </svg>
    );
  }

  const compact = variant === "icon";
  return (
    <svg
      viewBox="0 0 64 64"
      className={`app-logo app-logo-${variant} ${className}`.trim()}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      {...accessibility}
    >
      <path d="M7.5 37.5C10.7 24.2 28.3 13.9 45.1 17.2c9.2 1.8 14.1 7 11.4 13.1" stroke="#22D3EE" strokeWidth={compact ? 5.5 : 5} strokeLinecap="round" />
      <circle cx="32" cy="32" r="18" fill="#4F46E5" stroke="#312E81" strokeWidth="2" />
      <path d="M18.2 23.8c7.8 4.5 20.8 5 28.2.2" stroke="#A5F3FC" strokeWidth={compact ? 4 : 3.5} strokeLinecap="round" />
      <path d="M14.7 32.1c9.4 4.5 24.8 5 34.5-.8" stroke="#C4B5FD" strokeWidth={compact ? 4 : 3.5} strokeLinecap="round" />
      {!compact ? <path d="M17.5 40.2c8 3.6 20.4 3.7 28.3-1" stroke="#818CF8" strokeWidth="3.5" strokeLinecap="round" /> : null}
      <path d="M56.5 30.3c-3.5 13.2-21 22-37.8 18.3C9.8 46.7 5 41.7 7.5 37.5" stroke="#67E8F9" strokeWidth={compact ? 5.5 : 5} strokeLinecap="round" />
      {!compact ? <circle cx="42.8" cy="25.5" r="2.2" fill="#EEF2FF" opacity=".88" /> : null}
    </svg>
  );
}
