import Link from 'next/link'

export default function NotFound() {
  return (
    <div
      className="flex flex-col items-center justify-center h-screen gap-4 font-mono"
      style={{ background: '#0a0e13', color: '#7e97b0' }}
    >
      <div className="text-center">
        <p className="text-5xl font-bold mb-3" style={{ color: '#f0a500', letterSpacing: '0.1em' }}>
          404
        </p>
        <p className="text-sm font-semibold mb-1" style={{ color: '#dce7f0' }}>
          Page not found
        </p>
        <p className="text-xs" style={{ color: '#3e5068' }}>
          That route doesn't exist in the terminal.
        </p>
      </div>

      <Link
        href="/"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs transition-opacity hover:opacity-80"
        style={{
          background: '#171e27',
          border:     '1px solid #1e2732',
          color:      '#7e97b0',
        }}
      >
        ← Back to overview
      </Link>
    </div>
  )
}
