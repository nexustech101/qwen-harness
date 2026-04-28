import { useState } from "react"
import { LogIn, UserPlus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAuthStore } from "@/stores/auth"
import { toast } from "sonner"
import { ApiError } from "@/api/client"

interface AuthDialogProps {
  open: boolean
  mode: "login" | "register"
  onOpenChange: (open: boolean) => void
}

function errorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.body) as { detail?: string }
      return parsed.detail ?? fallback
    } catch {
      return error.body || fallback
    }
  }
  return error instanceof Error ? error.message : fallback
}

export function AuthDialog({ open, mode, onOpenChange }: AuthDialogProps) {
  const [tab, setTab] = useState(mode)
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)
  const loading = useAuthStore((s) => s.loading)

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setTab(mode)
        onOpenChange(next)
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Account</DialogTitle>
          <DialogDescription>Sign in to save chats and manage billing.</DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(value) => setTab(value as "login" | "register")}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="login">Sign in</TabsTrigger>
            <TabsTrigger value="register">Create account</TabsTrigger>
          </TabsList>
          <TabsContent value="login">
            <LoginForm
              loading={loading}
              onSubmit={async (email, password) => {
                try {
                  await login({ email, password })
                  toast.success("Signed in")
                  onOpenChange(false)
                } catch (error) {
                  toast.error(errorMessage(error, "Sign in failed"))
                }
              }}
            />
          </TabsContent>
          <TabsContent value="register">
            <RegisterForm
              loading={loading}
              onSubmit={async (email, fullName, password) => {
                try {
                  await register({ email, full_name: fullName, password })
                  toast.success("Account created")
                  onOpenChange(false)
                } catch (error) {
                  toast.error(errorMessage(error, "Account creation failed"))
                }
              }}
            />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

function LoginForm({
  loading,
  onSubmit,
}: {
  loading: boolean
  onSubmit: (email: string, password: string) => Promise<void>
}) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")

  return (
    <form
      className="space-y-4 pt-2"
      onSubmit={(e) => {
        e.preventDefault()
        void onSubmit(email.trim(), password)
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="signin-email">Email</Label>
        <Input id="signin-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="signin-password">Password</Label>
        <Input id="signin-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </div>
      <Button type="submit" className="w-full" disabled={loading}>
        <LogIn className="h-4 w-4" />
        {loading ? "Signing in..." : "Sign in"}
      </Button>
    </form>
  )
}

function RegisterForm({
  loading,
  onSubmit,
}: {
  loading: boolean
  onSubmit: (email: string, fullName: string, password: string) => Promise<void>
}) {
  const [email, setEmail] = useState("")
  const [fullName, setFullName] = useState("")
  const [password, setPassword] = useState("")

  return (
    <form
      className="space-y-4 pt-2"
      onSubmit={(e) => {
        e.preventDefault()
        void onSubmit(email.trim(), fullName.trim(), password)
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="signup-name">Full name</Label>
        <Input id="signup-name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="signup-email">Email</Label>
        <Input id="signup-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="signup-password">Password</Label>
        <Input id="signup-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </div>
      <Button type="submit" className="w-full" disabled={loading}>
        <UserPlus className="h-4 w-4" />
        {loading ? "Creating..." : "Create account"}
      </Button>
    </form>
  )
}
