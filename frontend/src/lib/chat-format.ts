const THINK_BLOCK_RE = /<think>[\s\S]*?<\/think>/gi
const FENCED_JSON_RE = /^```(?:json)?\s*([\s\S]*?)\s*```$/i

interface ParsedPayload {
  reasoning?: unknown
  response?: unknown
  status?: unknown
  tools?: unknown
}

export function formatAssistantContent(content: string): string {
  const stripped = stripThinking(content).trim()
  if (!stripped) return ""

  const jsonText = unwrapFencedJson(stripped)
  const parsed = parseJsonPayload(jsonText)
  if (parsed) {
    const response = asCleanString(parsed.response)
    if (response) return stripThinking(response).trim()

    const reasoning = asCleanString(parsed.reasoning)
    const tools = Array.isArray(parsed.tools) ? parsed.tools : []
    if (reasoning && tools.length === 0) return stripThinking(reasoning).trim()
  }

  return stripped
}

export function formatStreamingContent(content: string): string {
  const clean = formatAssistantContent(content)
  return clean || content.replace(THINK_BLOCK_RE, "").trim()
}

export function formatToolResult(value?: string, error?: string): string {
  const text = error || value || ""
  const clean = text.trim()
  if (!clean) return ""

  const parsed = parseJsonPayload(clean)
  if (parsed) {
    return JSON.stringify(parsed, null, 2)
  }
  return clean
}

function stripThinking(content: string): string {
  return content.replace(THINK_BLOCK_RE, "").trim()
}

function unwrapFencedJson(content: string): string {
  const match = content.match(FENCED_JSON_RE)
  return match ? match[1].trim() : content
}

function parseJsonPayload(content: string): ParsedPayload | null {
  try {
    const value = JSON.parse(content) as unknown
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return value as ParsedPayload
    }
  } catch {
    return null
  }
  return null
}

function asCleanString(value: unknown): string {
  return typeof value === "string" ? value.trim() : ""
}
