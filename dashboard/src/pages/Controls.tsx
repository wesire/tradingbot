import { useState, useEffect, useCallback } from "react"
import { AlertTriangle, Play, Pause, Power, Settings } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Dialog, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { apiClient } from "@/api/client"

const REFRESH_INTERVAL_MS = 30_000

export function Controls() {
  const [mode, setMode] = useState<'dry-run' | 'live'>('dry-run')
  const [botStatus, setBotStatus] = useState<'running' | 'paused'>('running')
  const [showModeDialog, setShowModeDialog] = useState(false)
  const [showKillDialog, setShowKillDialog] = useState(false)
  const [pendingMode, setPendingMode] = useState<'dry-run' | 'live'>('dry-run')
  const fetchStatus = useCallback(async () => {
    try {
      const status = await apiClient.getBotStatus()
      setMode(status.mode as 'dry-run' | 'live')
      setBotStatus(status.status === 'paused' ? 'paused' : 'running')
    } catch (err) {
      console.error('Failed to fetch bot status:', err)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchStatus])


  const handleModeToggle = (newMode: 'dry-run' | 'live') => {
    setPendingMode(newMode)
    setShowModeDialog(true)
  }

  const confirmModeChange = async () => {
    try {
      await apiClient.toggleMode(pendingMode)
      setMode(pendingMode)
      setShowModeDialog(false)
    } catch (error) {
      console.error('Failed to toggle mode:', error)
    }
  }

  const handlePauseResume = async () => {
    try {
      if (botStatus === 'running') {
        await apiClient.pauseBot()
        setBotStatus('paused')
      } else {
        await apiClient.resumeBot()
        setBotStatus('running')
      }
    } catch (error) {
      console.error('Failed to pause/resume bot:', error)
    }
  }

  const handleEmergencyStop = async () => {
    try {
      await apiClient.emergencyStop()
      setBotStatus('paused')
      setShowKillDialog(false)
    } catch (error) {
      console.error('Failed to execute emergency stop:', error)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Operator Controls</h1>
        <p className="text-muted-foreground">
          Manage bot operations and trading mode
        </p>
      </div>

      <Alert variant="warning">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Caution</AlertTitle>
        <AlertDescription>
          These controls directly affect bot operations. Use with care, especially when switching to live trading mode.
        </AlertDescription>
      </Alert>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Trading Mode
            </CardTitle>
            <CardDescription>
              Current mode: <Badge variant={mode === 'live' ? 'destructive' : 'secondary'}>{mode.toUpperCase()}</Badge>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Button
                variant={mode === 'dry-run' ? 'default' : 'outline'}
                className="w-full"
                onClick={() => handleModeToggle('dry-run')}
                disabled={mode === 'dry-run'}
              >
                Dry-Run Mode
              </Button>
              <p className="text-sm text-muted-foreground">
                Simulate trades without executing real orders
              </p>
            </div>
            <div className="space-y-2">
              <Button
                variant={mode === 'live' ? 'destructive' : 'outline'}
                className="w-full"
                onClick={() => handleModeToggle('live')}
                disabled={mode === 'live'}
              >
                Live Trading Mode
              </Button>
              <p className="text-sm text-muted-foreground">
                Execute real trades with actual funds
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Power className="h-5 w-5" />
              Bot Operations
            </CardTitle>
            <CardDescription>
              Status: <Badge variant={botStatus === 'running' ? 'success' : 'warning'}>{botStatus.toUpperCase()}</Badge>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Button
                variant="outline"
                className="w-full"
                onClick={handlePauseResume}
              >
                {botStatus === 'running' ? (
                  <>
                    <Pause className="mr-2 h-4 w-4" />
                    Pause Bot
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Resume Bot
                  </>
                )}
              </Button>
              <p className="text-sm text-muted-foreground">
                {botStatus === 'running' 
                  ? 'Temporarily pause all trading activity'
                  : 'Resume trading operations'}
              </p>
            </div>
            <div className="space-y-2">
              <Button
                variant="destructive"
                className="w-full"
                onClick={() => setShowKillDialog(true)}
              >
                <AlertTriangle className="mr-2 h-4 w-4" />
                Emergency Stop
              </Button>
              <p className="text-sm text-muted-foreground">
                Immediately close all positions and halt trading
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
          <CardDescription>Bot settings and parameters</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm font-medium">Max Position Size</p>
                <p className="text-2xl font-bold">$10,000</p>
              </div>
              <div>
                <p className="text-sm font-medium">Max Leverage</p>
                <p className="text-2xl font-bold">5x</p>
              </div>
              <div>
                <p className="text-sm font-medium">Stop Loss</p>
                <p className="text-2xl font-bold">2%</p>
              </div>
              <div>
                <p className="text-sm font-medium">Take Profit</p>
                <p className="text-2xl font-bold">5%</p>
              </div>
            </div>
            <Alert>
              <AlertDescription>
                Configuration changes require bot restart to take effect
              </AlertDescription>
            </Alert>
          </div>
        </CardContent>
      </Card>

      {/* Mode Change Confirmation Dialog */}
      <Dialog open={showModeDialog} onOpenChange={setShowModeDialog}>
        <DialogHeader>
          <DialogTitle>Confirm Mode Change</DialogTitle>
          <DialogDescription>
            Are you sure you want to switch to <strong>{pendingMode}</strong> mode?
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          {pendingMode === 'live' && (
            <Alert variant="warning">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Warning</AlertTitle>
              <AlertDescription>
                Live mode will execute real trades with actual funds. Ensure all configurations are correct before proceeding.
              </AlertDescription>
            </Alert>
          )}
          {pendingMode === 'dry-run' && (
            <Alert>
              <AlertDescription>
                Dry-run mode will simulate trades without executing real orders. This is safe for testing.
              </AlertDescription>
            </Alert>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setShowModeDialog(false)}>
            Cancel
          </Button>
          <Button 
            variant={pendingMode === 'live' ? 'destructive' : 'default'} 
            onClick={confirmModeChange}
          >
            Confirm
          </Button>
        </DialogFooter>
      </Dialog>

      {/* Emergency Stop Confirmation Dialog */}
      <Dialog open={showKillDialog} onOpenChange={setShowKillDialog}>
        <DialogHeader>
          <DialogTitle>Emergency Stop Confirmation</DialogTitle>
          <DialogDescription>
            This will immediately close all open positions and halt all trading operations.
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Critical Action</AlertTitle>
            <AlertDescription>
              This action cannot be undone. All open positions will be closed at market price, which may result in losses.
            </AlertDescription>
          </Alert>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setShowKillDialog(false)}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleEmergencyStop}>
            Execute Emergency Stop
          </Button>
        </DialogFooter>
      </Dialog>
    </div>
  )
}
