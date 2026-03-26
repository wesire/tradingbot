import { useState } from 'react'
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Settings, Brain, TrendingUp, BarChart2, Activity, Menu, X } from 'lucide-react'
import { Dashboard } from '@/pages/Dashboard'
import { Controls } from '@/pages/Controls'
import { AIOverview } from '@/pages/AIOverview'
import { Opportunities } from '@/pages/Opportunities'
import { MLInsights } from '@/pages/MLInsights'
import { cn } from '@/lib/utils'
import { TimeframeProvider, useTimeframe, TIMEFRAMES } from '@/context/TimeframeContext'
import type { Timeframe } from '@/context/TimeframeContext'

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/controls', icon: Settings, label: 'Controls' },
  { to: '/ai', icon: Brain, label: 'AI Advisor' },
  { to: '/opportunities', icon: TrendingUp, label: 'Opportunities' },
  { to: '/ml', icon: BarChart2, label: 'ML Insights' },
]

function NavLink({ to, icon: Icon, children, onClick }: {
  to: string
  icon: React.ElementType
  children: React.ReactNode
  onClick?: () => void
}) {
  const location = useLocation()
  const isActive = location.pathname === to

  return (
    <Link
      to={to}
      onClick={onClick}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
        isActive
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {children}
    </Link>
  )
}

function Sidebar({ onClose }: { onClose?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center justify-between border-b px-6">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-primary" />
          <h1 className="text-xl font-bold">TradingBot</h1>
        </div>
        {onClose && (
          <button onClick={onClose} className="lg:hidden p-1 rounded hover:bg-accent">
            <X className="h-5 w-5" />
          </button>
        )}
      </div>
      <nav className="flex-1 space-y-1 p-4">
        {NAV_ITEMS.map(item => (
          <NavLink key={item.to} to={item.to} icon={item.icon} onClick={onClose}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t p-4">
        <div className="text-xs text-muted-foreground">
          <p className="font-semibold">Status: Online</p>
          <p>Mode: Dry-Run</p>
        </div>
      </div>
    </div>
  )
}

function TimeframePicker() {
  const { timeframe, setTimeframe } = useTimeframe()
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {TIMEFRAMES.map(tf => (
        <button
          key={tf}
          onClick={() => setTimeframe(tf as Timeframe)}
          className={cn(
            "px-2 py-0.5 rounded text-xs font-medium transition-colors",
            timeframe === tf
              ? "bg-primary text-primary-foreground"
              : "bg-secondary text-secondary-foreground hover:bg-accent"
          )}
        >
          {tf}
        </button>
      ))}
    </div>
  )
}

function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="flex min-h-screen">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:block w-64 border-r bg-card shrink-0">
        <Sidebar />
      </aside>

      {/* Mobile Sidebar Overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="absolute left-0 top-0 bottom-0 w-64 bg-card border-r shadow-xl">
            <Sidebar onClose={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      {/* Main content */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Mobile top bar */}
        <header className="flex lg:hidden h-14 items-center gap-3 border-b bg-card px-4 shrink-0">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 rounded-lg hover:bg-accent"
            aria-label="Open navigation"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            <span className="font-semibold text-sm">TradingBot</span>
          </div>
        </header>

        {/* Desktop timeframe bar */}
        <div className="hidden lg:flex h-10 items-center border-b bg-card/50 px-6 gap-3 shrink-0">
          <span className="text-xs text-muted-foreground font-medium">Timeframe:</span>
          <TimeframePicker />
        </div>

        <main className="flex-1 overflow-auto">
          <div className="container mx-auto p-4 lg:p-6">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/controls" element={<Controls />} />
              <Route path="/ai" element={<AIOverview />} />
              <Route path="/opportunities" element={<Opportunities />} />
              <Route path="/ml" element={<MLInsights />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <TimeframeProvider>
        <Layout />
      </TimeframeProvider>
    </BrowserRouter>
  )
}

export default App
