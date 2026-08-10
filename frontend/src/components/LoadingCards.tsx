interface LoadingCardsProps {
  count: number;
  label: string;
}

export function LoadingCards({ count, label }: LoadingCardsProps) {
  return (
    <div
      role="status"
      aria-label={label}
      className="grid grid-cols-2 gap-4 md:grid-cols-4"
    >
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          className="h-24 animate-pulse rounded-xl border border-gray-800 bg-gray-800/40"
        />
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}
