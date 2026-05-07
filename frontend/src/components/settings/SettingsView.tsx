import { useEffect } from "react"
import { Settings } from "lucide-react"
import { Separator } from "@/components/ui/separator"
import { Badge } from "@/components/ui/badge"
import { useConfig } from "@/api/queries"
import { useUIStore } from "@/stores/ui"

function SettingRow({ label, value }: { label: string; value: string | number | undefined | null }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-mono text-right max-w-[55%] truncate" title={String(value ?? "—")}>
        {value ?? <span className="opacity-40">—</span>}
      </span>
    </div>
  )
}

export function SettingsView() {
  const { data: config, isLoading } = useConfig()
  const setCurrentProvider = useUIStore((s) => s.setCurrentProvider)

  useEffect(() => {
    if (config?.llm_provider) {
      setCurrentProvider(config.llm_provider)
    }
  }, [config?.llm_provider, setCurrentProvider])

  return (
    <div className="h-full overflow-y-auto p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
          <Settings className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-lg font-semibold">Settings</h1>
          <p className="text-sm text-muted-foreground">Current runtime configuration</p>
        </div>
      </div>

      <Separator className="mb-4" />

      {isLoading ? (
        <div className="text-sm text-muted-foreground py-8 text-center">Loading config…</div>
      ) : config ? (
        <div className="space-y-6">
          {/* Inference */}
          <section>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">Inference</h2>
            <div className="divide-y divide-border/30 rounded-xl border border-border/30 bg-card/40 px-4">
              <div className="flex items-start justify-between gap-4 py-3">
                <span className="text-sm text-muted-foreground">Provider</span>
                <Badge variant="secondary" className="font-mono text-xs">
                  {config.llm_provider}
                </Badge>
              </div>
              {config.llm_provider === "ollama" && (
                <SettingRow label="Ollama host" value={config.ollama_host} />
              )}
              <SettingRow label="Default model" value={config.default_model} />
            </div>
          </section>

          {/* About */}
          <section>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">About</h2>
            <div className="divide-y divide-border/30 rounded-xl border border-border/30 bg-card/40 px-4">
              <SettingRow label="App name" value={config.app_name} />
              <SettingRow label="API version" value={config.api_version} />
            </div>
          </section>
        </div>
      ) : (
        <div className="text-sm text-muted-foreground py-8 text-center">Unable to load configuration</div>
      )}
    </div>
  )
}
