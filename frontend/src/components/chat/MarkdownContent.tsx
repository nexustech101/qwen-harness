import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { CodeBlock, InlineCode } from "./CodeBlock"

const markdownComponents = {
  code({ className, children }: React.ComponentPropsWithoutRef<"code"> & { className?: string }) {
    const match = /language-(\w+)/.exec(className || "")
    const text = String(children).replace(/\n$/, "")

    if (match) {
      return <CodeBlock language={match[1]}>{text}</CodeBlock>
    }

    if (text.includes("\n")) {
      return <CodeBlock>{text}</CodeBlock>
    }

    return <InlineCode>{children}</InlineCode>
  },
  pre({ children }: React.ComponentPropsWithoutRef<"pre">) {
    return <>{children}</>
  },
}

export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="prose-chat text-sm leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
