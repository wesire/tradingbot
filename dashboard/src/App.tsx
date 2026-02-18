import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Settings, Brain, TrendingUp } from 'lucide-react'
import { Dashboard } from '@/pages/Dashboard'
import { Controls } from '@/pages/Controls'
import { AIOverview } from '@/pages/AIOverview'
import { Opportunities } from '@/pages/Opportunities'
import { cn } from '@/lib/utils'

function NavLink({ to, icon: Icon, children }: { to: string; icon: React.ElementType; children: React.ReactNode }) {
  const location = useLocation()
  const isActive = location.pathname === to

  return (
    <Link
      to={to}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
        isActive
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      )}
    >
      <Icon className="h-4 w-4" />
      {children}
    </Link>
  )
}

function Layout() {
  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-64 border-r bg-card">
        <div className="flex h-full flex-col">
          <div className="flex h-16 items-center border-b px-6">
            <h1 className="text-xl font-bold">Trading Bot</h1>
          </div>
          <nav className="flex-1 space-y-1 p-4">
            <NavLink to="/" icon={LayoutDashboard}>
              Dashboard
            </NavLink>
            <NavLink to="/controls" icon={Settings}>
              Controls
            </NavLink>
            <NavLink to="/ai" icon={Brain}>
              AI Advisor
            </NavLink>
            <NavLink to="/opportunities" icon={TrendingUp}>
              Opportunities
            </NavLink>
          </nav>
          <div className="border-t p-4">
            <div className="text-xs text-muted-foreground">
              <p className="font-semibold">Status: Online</p>
              <p>Mode: Dry-Run</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="container mx-auto p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/controls" element={<Controls />} />
            <Route path="/ai" element={<AIOverview />} />
            <Route path="/opportunities" element={<Opportunities />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  )
}

export default App
