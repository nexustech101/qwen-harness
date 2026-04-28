import { useState } from "react"
import type { ReactNode } from "react"
import { CreditCard, LogIn, LogOut, Moon, Settings, Sun, User, UserPlus } from "lucide-react"
import { useUIStore } from "@/stores/ui"
import { useAuthStore } from "@/stores/auth"
import { useWSStore } from "@/stores/websocket"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { AuthDialog } from "@/components/account/AuthDialog"
import { AccountDialog } from "@/components/account/AccountDialog"
import { BillingDialog } from "@/components/account/BillingDialog"
import { toast } from "sonner"

export function TopNav() {
  const { theme, toggleTheme } = useUIStore()
  const [accountOpen, setAccountOpen] = useState(false)
  const [authOpen, setAuthOpen] = useState(false)
  const [authMode, setAuthMode] = useState<"login" | "register">("login")
  const [profileOpen, setProfileOpen] = useState(false)
  const [billingOpen, setBillingOpen] = useState(false)
  const user = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const logout = useAuthStore((s) => s.logout)
  const disconnect = useWSStore((s) => s.disconnect)
  const setActiveSession = useUIStore((s) => s.setActiveSession)

  const openAuth = (mode: "login" | "register") => {
    setAuthMode(mode)
    setAuthOpen(true)
    setAccountOpen(false)
  }

  return (
    <header className="flex h-11 shrink-0 items-center justify-end gap-2 px-4 border-b border-border/30">
      <button
        onClick={toggleTheme}
        className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      >
        {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>
      <Popover open={accountOpen} onOpenChange={setAccountOpen}>
        <PopoverTrigger asChild>
          <button
            className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/80 text-primary-foreground hover:bg-primary transition-colors"
            title={isAuthenticated ? user?.email : "Account"}
          >
            <User className="h-3.5 w-3.5" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-64 p-2">
          {isAuthenticated && user ? (
            <div className="space-y-1">
              <div className="px-2 py-2">
                <div className="truncate text-sm font-medium">{user.full_name || user.email}</div>
                <div className="truncate text-xs text-muted-foreground">{user.email}</div>
              </div>
              <MenuButton
                icon={<Settings className="h-4 w-4" />}
                label="Account"
                onClick={() => {
                  setProfileOpen(true)
                  setAccountOpen(false)
                }}
              />
              <MenuButton
                icon={<CreditCard className="h-4 w-4" />}
                label="Billing"
                onClick={() => {
                  setBillingOpen(true)
                  setAccountOpen(false)
                }}
              />
              <div className="my-1 border-t border-border/50" />
              <MenuButton
                icon={<LogOut className="h-4 w-4" />}
                label="Sign out"
                onClick={async () => {
                  setAccountOpen(false)
                  await logout()
                  disconnect()
                  setActiveSession(null)
                  toast.success("Signed out")
                }}
              />
            </div>
          ) : (
            <div className="space-y-1">
              <div className="px-2 py-2 text-xs text-muted-foreground">
                Continue as a guest, or sign in to save chat history.
              </div>
              <MenuButton icon={<LogIn className="h-4 w-4" />} label="Sign in" onClick={() => openAuth("login")} />
              <MenuButton icon={<UserPlus className="h-4 w-4" />} label="Create account" onClick={() => openAuth("register")} />
            </div>
          )}
        </PopoverContent>
      </Popover>
      <AuthDialog key={authMode} open={authOpen} mode={authMode} onOpenChange={setAuthOpen} />
      <AccountDialog open={profileOpen} onOpenChange={setProfileOpen} />
      <BillingDialog open={billingOpen} onOpenChange={setBillingOpen} />
    </header>
  )
}

function MenuButton({
  icon,
  label,
  onClick,
}: {
  icon: ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <Button variant="ghost" className="h-8 w-full justify-start px-2 text-sm" onClick={onClick}>
      {icon}
      {label}
    </Button>
  )
}
