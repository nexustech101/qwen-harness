import { CreditCard } from "lucide-react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"

interface BillingDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function BillingDialog({ open, onOpenChange }: BillingDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CreditCard className="h-4 w-4" />
            Billing
          </DialogTitle>
          <DialogDescription>Billing is not available in this version.</DialogDescription>
        </DialogHeader>
      </DialogContent>
    </Dialog>
  )
}
