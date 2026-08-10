import clsx from "clsx";
import { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
}

export function Button({
  variant = "primary",
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      className={clsx(
        "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-solar-400",
        "focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary"
          ? "bg-solar-500 text-gray-950 hover:bg-solar-400"
          : "border border-gray-700 bg-gray-800/60 text-gray-200 hover:border-gray-600 hover:text-white",
        className
      )}
    />
  );
}
