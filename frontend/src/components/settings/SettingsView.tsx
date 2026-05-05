import { Settings } from "lucide-react"
import { Separator } from "@/components/ui/separator"
import { useConfig } from "@/api/queries"

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
              <SettingRow label="Ollama host" value={config.ollama_host} />
              <SettingRow label="Default model" value={config.model} />
              <SettingRow label="Planner model" value={config.planner_model} />
              <SettingRow label="Coder model" value={config.coder_model} />
            </div>
          </section>

          {/* Execution */}
          <section>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">Execution</h2>
            <div className="divide-y divide-border/30 rounded-xl border border-border/30 bg-card/40 px-4">
              <SettingRow label="Max turns" value={config.max_turns} />
              <SettingRow label="Max messages" value={config.max_messages} />
              <SettingRow label="Sub-agent max turns" value={config.sub_agent_max_turns} />
              <SettingRow label="Max concurrent agents" value={config.max_concurrent_agents} />
            </div>
          </section>

          {/* Routing */}
          <section>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">Routing</h2>
            <div className="divide-y divide-border/30 rounded-xl border border-border/30 bg-card/40 px-4">
              <SettingRow label="Router mode" value={config.router_mode} />
              <SettingRow label="Context mode" value={config.context_mode} />
              <SettingRow label="Tool scope mode" value={config.tool_scope_mode} />
            </div>
          </section>

          {/* Workspace */}
          <section>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">Workspace</h2>
            <div className="divide-y divide-border/30 rounded-xl border border-border/30 bg-card/40 px-4">
              <SettingRow label="Home" value={config.workspace_home} />
              <SettingRow label="Projects dir" value={config.workspace_projects_dir} />
            </div>
          </section>
        </div>
      ) : (
        <div className="text-sm text-muted-foreground py-8 text-center">Unable to load configuration</div>
      )}
    </div>
  )
}
