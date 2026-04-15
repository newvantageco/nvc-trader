'use client'

import { useEffect, useState } from 'react'
import { DesktopSidebar, MobileNav } from '@/components/Sidebar'
import ToastContainer from '@/components/Toast'
import CommandPalette from '@/components/CommandPalette'
import SystemStatusBanner from '@/components/SystemStatusBanner'
import PageTransition from '@/components/PageTransition'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [paletteOpen, setPaletteOpen] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setPaletteOpen(prev => !prev)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
      <DesktopSidebar onOpenPalette={() => setPaletteOpen(true)} />
      <div className="flex flex-col flex-1 overflow-hidden min-w-0">
        {/* SystemStatusBanner sits above all page content, under the sidebar */}
        <SystemStatusBanner />
        {/* pb-14 leaves room for mobile bottom nav */}
        <main className="flex-1 overflow-hidden pb-14 sm:pb-0 min-w-0">
          <PageTransition>{children}</PageTransition>
        </main>
      </div>
      <MobileNav />
      <ToastContainer />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  )
}
