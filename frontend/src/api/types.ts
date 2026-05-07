// Types matching BACKEND_SPEC.md exactly

export interface HealthResponse {
  status: string
  service: string
  time: string | null
  ip: string | null
  request_id: string | null
  ollama_connected: boolean
  version: string
}

export interface UserPublic {
  id: number
  email: string
  full_name: string
  is_active: boolean
  is_admin: boolean
  created_at: string
  updated_at: string
  last_login_at: string | null
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: "bearer"
  expires_in: number
}

export interface RegisterRequest {
  email: string
  full_name: string
  password: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

export interface BillingSubscriptionPublic {
  user_id: number
  stripe_customer_id: string | null
  stripe_subscription_id: string | null
  subscription_status: string | null
  price_id: string | null
  current_period_end: string | null
  cancel_at_period_end: boolean
  has_access: boolean
  updated_at: string | null
}

export interface BillingCheckoutResponse {
  checkout_url: string
}

export interface BillingPortalResponse {
  portal_url: string
}

export interface ConfigResponse {
  app_name: string
  api_version: string
  ollama_host: string
  default_model: string
  mcp_server_name: string
  llm_provider: "ollama" | "openai" | "anthropic"
}

export type LLMProvider = "ollama" | "openai" | "anthropic"

export interface OllamaModel {
  name: string
  size: number
  modified_at: string
  family: string | null
  parameter_size: string | null
  quantization_level: string | null
}

export interface CreateSessionRequest {
  model?: string | null
  title?: string | null
}

export interface SessionStats {
  total_turns: number
  total_tool_calls: number
  elapsed_seconds: number
  files_modified: string[]
  message_count: number
}

export interface AgentSummary {
  name: string
  status: string
  model: string
  turns_used: number
  max_turns: number
  goal: string
}

export interface SessionResponse {
  id: string
  title: string | null
  model: string
  status: "idle" | "running" | "error"
  created_at: string
  updated_at: string
  message_count: number
}

export interface ResultMetadata {
  turns: number
  reason: string
  tool_calls_made: number
  files_modified: string[]
  elapsed_seconds: number
  attachments?: AttachmentRef[]
}

export interface AttachmentRef {
  filename: string
  mime_type: string
  size: number
}

export interface MessageResponse {
  role: "user" | "assistant" | "error" | "system"
  content: string
  timestamp: number | null
  metadata: ResultMetadata | null
  attachments?: AttachmentRef[]
}

export interface ToolCall {
  name: string
  args: Record<string, unknown>
}

export interface AgentDetailResponse extends AgentSummary {
  messages: MessageResponse[]
  tool_calls: ToolCall[]
  files_modified: string[]
}

export interface FileEntry {
  name: string
  path: string
  type: "file" | "directory"
  size: number | null
  children: FileEntry[] | null
}

export interface FileContent {
  path: string
  content: string
  size: number
  lines: number
}

export interface PromptRequest {
  prompt: string
  direct?: boolean
  attachment_ids?: string[]
}

export interface SendPromptRequest {
  prompt: string
  attachment_ids?: string[]
}

export interface PromptAccepted {
  status: string
  session_id: string
}

export interface UploadMeta {
  id: string
  filename: string
  mime_type: string
  size: number
  url: string
  thumbnail_url: string | null
}

export interface UploadResponse {
  uploads: UploadMeta[]
}

export interface ToolMeta {
  name: string
  description: string
}

export interface ToolInvokeRequest {
  name: string
  args: Record<string, unknown>
}

// ── Workflow types ─────────────────────────────────────────────────────────────

export interface WorkflowStep {
  id: string
  type: "prompt"
  title: string
  prompt: string
  model?: string
  x: number
  y: number
}

export interface WorkflowEdge {
  id: string
  source: string
  target: string
}

export interface WorkflowDefinition {
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  interval_seconds?: number | null
}

export interface WorkflowResponse {
  id: string
  name: string
  description: string
  definition: WorkflowDefinition
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface WorkflowRunResponse {
  id: string
  workflow_id: string
  status: "pending" | "running" | "done" | "error"
  result: Record<string, unknown> | null
  started_at: string
  finished_at: string | null
}

export interface WorkflowExecuteResponse {
  run_id: string
  session_id: string
  steps: Array<{ id: string; title: string; prompt: string }>
}

// WebSocket event types
export interface WSEvent {
  type: string
  agent: string
  data: Record<string, unknown>
  timestamp: number
}

// Chat item types for rendering
export type ChatItem =
  | { type: "user"; content: string; timestamp: number; attachments?: AttachmentRef[] }
  | { type: "assistant"; content: string; timestamp: number; metadata?: ResultMetadata }
  | { type: "reasoning"; content: string; agent: string; timestamp: number }
  | { type: "tool_call"; name: string; args: Record<string, unknown>; result?: string; success?: boolean; error?: string; agent: string; id: string; timestamp: number }
  | { type: "error"; content: string; agent: string; timestamp: number }
  | { type: "recovery"; attempt: number; reason: string; agent: string; timestamp: number }
  | { type: "turn_divider"; turn: number; agent: string; timestamp: number }
  | { type: "agent_start"; agent: string; model: string; goal: string; timestamp: number }
  | { type: "agent_done"; agent: string; reason: string; turns: number; elapsed: number; timestamp: number }
