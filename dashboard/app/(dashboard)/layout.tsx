import Sidebar from '@/components/Sidebar'
import ToastContainer from '@/components/Toast'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="flex-1 overflow-hidden">
        {children}
      </main>
      <ToastContainer />
    </div>
  )
}
