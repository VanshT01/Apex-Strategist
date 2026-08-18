export function LoadingSkeleton({
  label = "Loading race data",
}: {
  label?: string;
}) {
  return (
    <div role="status" className="panel animate-pulse p-8 text-sm text-mist">
      {label}…
    </div>
  );
}

export function ErrorState({
  message,
  action,
}: {
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-red-400/30 bg-red-400/10 p-5 text-sm text-red-200"
    >
      <strong>Data unavailable.</strong> {message}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="panel p-10 text-center text-mist">{children}</div>;
}
