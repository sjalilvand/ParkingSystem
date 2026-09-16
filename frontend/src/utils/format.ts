export function faDate(iso?: string | null): string {
  if (!iso) return '-'
  try {
    return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(iso))
  } catch { return iso }
}

export function money(amount?: number | null): string {
  if (amount == null) return '۰'
  return new Intl.NumberFormat('fa-IR').format(amount) + ' ریال'
}

export function durationFa(seconds?: number | null): string {
  if (!seconds || seconds <= 0) return 'کمتر از یک دقیقه'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const parts: string[] = []
  if (h) parts.push(`${h} ساعت`)
  if (m) parts.push(`${m} دقیقه`)
  return parts.join(' و ')
}