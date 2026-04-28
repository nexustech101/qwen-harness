import { CreditCard, ExternalLink, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useBillingSubscription, useCheckoutSession, usePortalSession } from "@/api/queries"
import { ApiError } from "@/api/client"
import { toast } from "sonner"

interface BillingDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function providerMessage(error: unknown) {
  if (error instanceof ApiError && [502, 503].includes(error.status)) {
    return "Billing provider is unavailable or not configured."
  }
  return "Billing action failed."
}

export function BillingDialog({ open, onOpenChange }: BillingDialogProps) {
  const subscription = useBillingSubscription(open)
  const checkout = useCheckoutSession()
  const portal = usePortalSession()
  const noSubscription = subscription.error instanceof ApiError && subscription.error.status === 404
  const providerUnavailable = subscription.error instanceof ApiError && [502, 503].includes(subscription.error.status)
  const data = subscription.data

  const status = data?.subscription_status ?? "none"
  const hasAccess = data?.has_access ?? false

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Billing</DialogTitle>
          <DialogDescription>Subscription access for saved coding sessions.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-lg border border-border/50 bg-card/40 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Subscription</span>
              </div>
              {subscription.isLoading ? (
                <Badge variant="secondary">Loading</Badge>
              ) : hasAccess ? (
                <Badge variant="success">{status}</Badge>
              ) : (
                <Badge variant="secondary">{noSubscription ? "none" : status}</Badge>
              )}
            </div>

            <div className="mt-3 text-sm text-muted-foreground">
              {subscription.isLoading && "Checking subscription..."}
              {noSubscription && "No active subscription."}
              {providerUnavailable && "Billing provider is unavailable or not configured."}
              {data && (
                <>
                  {data.current_period_end
                    ? `Current period ends ${new Date(data.current_period_end).toLocaleDateString()}.`
                    : hasAccess
                      ? "Subscription access is active."
                      : "Subscription access is inactive."}
                  {data.cancel_at_period_end && " Cancellation is scheduled at period end."}
                </>
              )}
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              disabled={portal.isPending || providerUnavailable}
              onClick={async () => {
                try {
                  const result = await portal.mutateAsync()
                  window.location.href = result.portal_url
                } catch (error) {
                  toast.error(providerMessage(error))
                }
              }}
            >
              {portal.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ExternalLink className="h-4 w-4" />}
              Manage
            </Button>
            <Button
              disabled={checkout.isPending || providerUnavailable}
              onClick={async () => {
                try {
                  const result = await checkout.mutateAsync(null)
                  window.location.href = result.checkout_url
                } catch (error) {
                  toast.error(providerMessage(error))
                }
              }}
            >
              {checkout.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CreditCard className="h-4 w-4" />}
              Upgrade
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
