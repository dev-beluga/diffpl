export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-20 text-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-gold-soft border-t-gold-deep" />
      <div className="text-sm text-ink-soft">{label}</div>
    </div>
  );
}

export function Failed({ message }: { message: string }) {
  return (
    <div className="rounded-2xl bg-rose-50 p-6 text-sm text-rose-800 ring-1 ring-rose-200">
      Could not load this: {message}. Is the API running (<code>uvicorn diffpl.api.app:app</code>)?
    </div>
  );
}
