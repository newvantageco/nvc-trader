import { DesktopSidebar, MobileNav } from '@/components/Sidebar'
import ToastContainer from '@/components/Toast'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
      <DesktopSidebar />
      {/* pb-14 on mobile leaves room for the bottom nav bar */}
      <main className="flex-1 overflow-hidden pb-14 sm:pb-0">
        {children}
      </main>
      <MobileNav />
      <ToastContainer />
    </div>
  )
}
