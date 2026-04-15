/**
 * loading.tsx — route-level skeleton shown by Next.js App Router
 * while the page chunk and its data are loading.
 */
export default function DashboardLoading() {
  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-base)' }}>
      {/* Header skeleton */}
      <div
        className="px-6 py-3 border-b flex items-center justify-between flex-shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
      >
        <div className="flex flex-col gap-1.5">
          <div className="skeleton" style={{ width: 120, height: 14 }} />
          <div className="skeleton" style={{ width: 200, height: 10 }} />
        </div>
        <div className="skeleton" style={{ width: 72, height: 28, borderRadius: 6 }} />
      </div>

      {/* Body skeleton */}
      <div className="flex-1 p-6 flex flex-col gap-4 overflow-hidden">
        <div className="skeleton" style={{ width: '100%', height: 180, borderRadius: 8 }} />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="skeleton"
              style={{ height: 72, borderRadius: 8 }}
            />
          ))}
        </div>
        <div className="skeleton" style={{ width: '100%', height: 240, borderRadius: 8 }} />
      </div>
    </div>
  )
}
