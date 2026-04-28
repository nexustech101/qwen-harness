import { useState } from "react"
import { KeyRound, Mail, User } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuthStore } from "@/stores/auth"
import { toast } from "sonner"
import { ApiError } from "@/api/client"

interface AccountDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.body) as { detail?: string }
      return parsed.detail ?? "Password update failed"
    } catch {
      return error.body || "Password update failed"
    }
  }
  return error instanceof Error ? error.message : "Password update failed"
}

export function AccountDialog({ open, onOpenChange }: AccountDialogProps) {
  const user = useAuthStore((s) => s.user)
  const changePassword = useAuthStore((s) => s.changePassword)
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [saving, setSaving] = useState(false)

  const reset = () => {
    setCurrentPassword("")
    setNewPassword("")
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset()
        onOpenChange(next)
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Account</DialogTitle>
          <DialogDescription>Profile and password settings.</DialogDescription>
        </DialogHeader>

        {user && (
          <div className="space-y-3 rounded-lg border border-border/50 bg-card/40 p-3 text-sm">
            <div className="flex items-center gap-2">
              <User className="h-4 w-4 text-muted-foreground" />
              <span>{user.full_name || "Unnamed user"}</span>
            </div>
            <div className="flex items-center gap-2 text-muted-foreground">
              <Mail className="h-4 w-4" />
              <span>{user.email}</span>
            </div>
          </div>
        )}

        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault()
            setSaving(true)
            try {
              await changePassword({
                current_password: currentPassword,
                new_password: newPassword,
              })
              toast.success("Password updated")
              reset()
            } catch (error) {
              toast.error(errorMessage(error))
            } finally {
              setSaving(false)
            }
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="current-password">Current password</Label>
            <Input
              id="current-password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-password">New password</Label>
            <Input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
          </div>
          <Button type="submit" disabled={saving || !currentPassword || !newPassword}>
            <KeyRound className="h-4 w-4" />
            {saving ? "Updating..." : "Change password"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
