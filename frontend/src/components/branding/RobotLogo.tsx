import { cn } from "@/lib/utils"

interface RobotLogoProps {
  className?: string
  size?: number
}

/**
 * Minimal geometric robot head logo for Qwen Coder.
 * Pure SVG — no external assets needed.
 */
export function RobotLogo({ className, size = 48 }: RobotLogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("shrink-0", className)}
    >
      {/* Antenna */}
      <line x1="32" y1="4" x2="32" y2="14" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="32" cy="4" r="3" fill="currentColor" opacity="0.6" />

      {/* Head */}
      <rect x="12" y="14" width="40" height="34" rx="8" stroke="currentColor" strokeWidth="2.5" fill="none" />

      {/* Eyes */}
      <circle cx="24" cy="28" r="4.5" fill="currentColor" opacity="0.85" />
      <circle cx="40" cy="28" r="4.5" fill="currentColor" opacity="0.85" />

      {/* Eye glints */}
      <circle cx="22.5" cy="26.5" r="1.5" fill="currentColor" opacity="0.3" />
      <circle cx="38.5" cy="26.5" r="1.5" fill="currentColor" opacity="0.3" />

      {/* Mouth — friendly curve */}
      <path d="M24 38 Q32 44 40 38" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" fill="none" />

      {/* Ears */}
      <rect x="4" y="22" width="8" height="14" rx="3" stroke="currentColor" strokeWidth="2" fill="none" />
      <rect x="52" y="22" width="8" height="14" rx="3" stroke="currentColor" strokeWidth="2" fill="none" />

      {/* Neck bolts */}
      <circle cx="24" cy="52" r="2" fill="currentColor" opacity="0.4" />
      <circle cx="40" cy="52" r="2" fill="currentColor" opacity="0.4" />

      {/* Jaw line accent */}
      <line x1="20" y1="48" x2="44" y2="48" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.3" />
    </svg>
  )
}
