import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconBase({ children, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {children}
    </svg>
  );
}

export function HomeIcon(props: IconProps) {
  return <IconBase {...props}><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9M9 20v-7h6v7" /></IconBase>;
}

export function LibraryIcon(props: IconProps) {
  return <IconBase {...props}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v17H6.5A2.5 2.5 0 0 0 4 22Z" /><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v17h4.5A2.5 2.5 0 0 1 20 22Z" /></IconBase>;
}

export function BuilderIcon(props: IconProps) {
  return <IconBase {...props}><path d="M4 4h16v16H4z" /><path d="M8 8h8M8 12h5M8 16h7" /></IconBase>;
}

export function HistoryIcon(props: IconProps) {
  return <IconBase {...props}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></IconBase>;
}

export function AnalyticsIcon(props: IconProps) {
  return <IconBase {...props}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></IconBase>;
}

export function TransferIcon(props: IconProps) {
  return <IconBase {...props}><path d="M7 7h12M15 3l4 4-4 4M17 17H5M9 13l-4 4 4 4" /></IconBase>;
}

export function ReadingIcon(props: IconProps) {
  return <IconBase {...props}><path d="M5 4h14v16H5z" /><path d="M8 8h8M8 12h8M8 16h5" /></IconBase>;
}

export function HeadphonesIcon(props: IconProps) {
  return <IconBase {...props}><path d="M4 14v-2a8 8 0 0 1 16 0v2" /><path d="M4 14h3v6H5a1 1 0 0 1-1-1ZM20 14h-3v6h2a1 1 0 0 0 1-1Z" /></IconBase>;
}

export function SparkleIcon(props: IconProps) {
  return <IconBase {...props}><path d="M12 3c.5 4.8 2.2 6.5 7 7-4.8.5-6.5 2.2-7 7-.5-4.8-2.2-6.5-7-7 4.8-.5 6.5-2.2 7-7Z" /><path d="M19 16c.2 1.7.8 2.3 2.5 2.5-1.7.2-2.3.8-2.5 2.5-.2-1.7-.8-2.3-2.5-2.5 1.7-.2 2.3-.8 2.5-2.5Z" /></IconBase>;
}

export function SearchIcon(props: IconProps) {
  return <IconBase {...props}><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></IconBase>;
}

export function PlusIcon(props: IconProps) {
  return <IconBase {...props}><path d="M12 5v14M5 12h14" /></IconBase>;
}

export function ArrowIcon(props: IconProps) {
  return <IconBase {...props}><path d="M5 12h14M14 7l5 5-5 5" /></IconBase>;
}

export function MoreIcon(props: IconProps) {
  return <IconBase {...props}><circle cx="5" cy="12" r="1" fill="currentColor" /><circle cx="12" cy="12" r="1" fill="currentColor" /><circle cx="19" cy="12" r="1" fill="currentColor" /></IconBase>;
}

export function CheckIcon(props: IconProps) {
  return <IconBase {...props}><path d="m5 12 4 4L19 6" /></IconBase>;
}

export function AlertIcon(props: IconProps) {
  return <IconBase {...props}><path d="M12 3 2.5 20h19Z" /><path d="M12 9v4M12 17h.01" /></IconBase>;
}

export function ArchiveIcon(props: IconProps) {
  return <IconBase {...props}><path d="M4 7h16v13H4zM3 3h18v4H3zM9 11h6" /></IconBase>;
}

export function TrashIcon(props: IconProps) {
  return <IconBase {...props}><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5" /></IconBase>;
}
