import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatTime(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}m ${secs.toFixed(0)}s`
}

export function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString()
}

export function getFileExtension(path: string): string {
  const parts = path.split(".")
  return parts.length > 1 ? parts[parts.length - 1] : ""
}

export function getFileName(path: string): string {
  const parts = path.split("/")
  return parts[parts.length - 1]
}
