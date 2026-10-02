import { useEffect, useState } from 'react'
import { TextField } from '@mui/material'

const _div = (a: number, b: number) => Math.floor(a / b)

export function gregorianToJalali(gy: number, gm: number, gd: number) {
  const gDm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
  let jy = gy <= 1600 ? 0 : 979
  gy -= gy <= 1600 ? 621 : 1600
  const gy2 = gm > 2 ? gy + 1 : gy
  let days = 365 * gy + _div(gy2 + 3, 4) - _div(gy2 + 99, 100) + _div(gy2 + 399, 400) - 80 + gd + gDm[gm - 1]
  jy += 33 * _div(days, 12053); days %= 12053
  jy += 4 * _div(days, 1461); days %= 1461
  if (days > 365) { jy += _div(days - 1, 365); days = (days - 1) % 365 }
  const jm = days < 186 ? 1 + _div(days, 31) : 7 + _div(days - 186, 30)
  const jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30)
  return { jy, jm, jd }
}

export function jalaliToGregorian(jy: number, jm: number, jd: number) {
  let gy = jy <= 979 ? 621 : 1600
  jy -= jy <= 979 ? 0 : 979
  let days = 365 * jy + _div(jy, 33) * 8 + _div((jy % 33) + 3, 4) + 78 + jd + (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186)
  gy += 400 * _div(days, 146097); days %= 146097
  if (days > 36524) { gy += 100 * _div(--days, 36524); days %= 36524; if (days >= 365) days++ }
  gy += 4 * _div(days, 1461); days %= 1461
  if (days > 365) { gy += _div(days - 1, 365); days = (days - 1) % 365 }
  let gd = days + 1
  const leap = (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0
  const md = [0, 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  let gm = 1
  while (gm <= 12 && gd > md[gm]) { gd -= md[gm]; gm++ }
  return { gy, gm, gd }
}

export function formatJalali(dt: Date, withTime = true): string {
  const j = gregorianToJalali(dt.getFullYear(), dt.getMonth() + 1, dt.getDate())
  const p2 = (n: number) => String(n).padStart(2, '0')
  return `${j.jy}/${p2(j.jm)}/${p2(j.jd)}${withTime ? ` ${p2(dt.getHours())}:${p2(dt.getMinutes())}` : ''}`
}

export function parseJalaliText(txt: string): Date | null {
  const m = txt.trim().match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?$/)
  if (!m) return null
  const jy = +m[1], jm = +m[2], jd = +m[3]
  if (jm < 1 || jm > 12) return null
  const leapJ = [1, 5, 9, 13, 17, 22, 26, 30].includes(jy % 33)
  const dim = jm <= 6 ? 31 : jm <= 11 ? 30 : leapJ ? 30 : 29
  if (jd < 1 || jd > dim) return null
  const hh = m[4] ? +m[4] : 0
  const mi = m[5] ? +m[5] : 0
  if (hh > 23 || mi > 59) return null
  const g = jalaliToGregorian(jy, jm, jd)
  return new Date(g.gy, g.gm - 1, g.gd, hh, mi)
}

export default function JalaliDateTime({ label, value, onChange, required }:
  { label: string; value: string | null | undefined; onChange: (iso: string) => void; required?: boolean }) {
  const [txt, setTxt] = useState('')
  const [bad, setBad] = useState(false)
  useEffect(() => {
    if (value) {
      const d = new Date(value)
      if (!isNaN(d.getTime())) setTxt(formatJalali(d))
    } else setTxt('')
  }, [value])
  return (
    <TextField size="small" label={`${label} (شمسی)`} required={required}
      placeholder="۱۴۰۵/۰۷/۱۰ ۰۸:۳۰" value={txt} error={bad}
      helperText={bad ? 'قالب صحیح: ۱۴۰۵/۰۷/۱۰ ۰۸:۳۰' : ' '}
      onChange={(e) => {
        const t = e.target.value
        setTxt(t)
        const d = parseJalaliText(t)
        setBad(!!t.trim() && !d)
        if (d) onChange(d.toISOString())
        else if (!t.trim()) onChange('')
      }} sx={{ minWidth: 230 }} />
  )
}
