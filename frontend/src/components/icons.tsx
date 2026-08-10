import clsx from "clsx";
import { ReactNode } from "react";

interface IconProps {
  className?: string;
}

function Glyph({
  className,
  children,
}: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={clsx("h-5 w-5", className)}
    >
      {children}
    </svg>
  );
}

export function SunIcon({ className }: IconProps) {
  return (
    <Glyph className={className}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" />
    </Glyph>
  );
}

export function PlugIcon({ className }: IconProps) {
  return (
    <Glyph className={className}>
      <path d="M9 3v5M15 3v5" />
      <path d="M6 8h12v2.5a6 6 0 0 1-12 0V8Z" />
      <path d="M12 16.5V21" />
    </Glyph>
  );
}

export function TrendIcon({ className }: IconProps) {
  return (
    <Glyph className={className}>
      <path d="M3 18l5.5-5.5 3.5 3L21 6" />
      <path d="M16 6h5v5" />
    </Glyph>
  );
}

export function AlertIcon({ className }: IconProps) {
  return (
    <Glyph className={className}>
      <path d="M12 4.5 21 20H3L12 4.5Z" />
      <path d="M12 10.5v4M12 17.5h.01" />
    </Glyph>
  );
}

export function CheckIcon({ className }: IconProps) {
  return (
    <Glyph className={className}>
      <path d="M4 12.5l5 5L20 6.5" />
    </Glyph>
  );
}

export function ArrowRightIcon({ className }: IconProps) {
  return (
    <Glyph className={className}>
      <path d="M4 12h15M13 6l6 6-6 6" />
    </Glyph>
  );
}

export function SpinnerIcon({ className }: IconProps) {
  return (
    <Glyph className={clsx("animate-spin", className)}>
      <circle cx="12" cy="12" r="9" className="opacity-25" />
      <path d="M21 12a9 9 0 0 0-9-9" />
    </Glyph>
  );
}
