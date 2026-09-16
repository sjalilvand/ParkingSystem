// الگوریتم استاندارد jalaali (MIT) — تبدیل دقیق تقویم جلالی/میلادی

const breaks = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]

function div(a: number, b: number): number { return ~~(a / b) }
function mod(a: number, b: number): number { return a - ~~(a / b) * b }

function jalCal(jy: number): { leap: number; gy: number; march: number } {
  const bl = breaks.length
  const gy = jy + 621
  let leapJ = -14
  let jp = breaks[0]
  let jump = 0
  for (let i = 1; i < bl; i += 1) {
    const jm = breaks[i]
    jump = jm - jp
    if (jy < jm) break
    leapJ = leapJ + div(jump, 33) * 8 + div(mod(jump, 33), 4)
    jp = jm
  }
  let n = jy - jp
  leapJ = leapJ + div(n, 33) * 8 + div(mod(n, 33) + 3, 4)
  if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1
  const leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150
  const march = 20 + leapJ - leapG
  if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33
  let leap = mod(mod(n + 1, 33) - 1, 4)
  if (leap === -1) leap = 4
  return { leap, gy, march }
}

export function g2d(gy: number, gm: number, gd: number): number {
  let d = div((gy + div(gm - 8, 6) + 100100) * 1461, 4) + div(153 * mod(gm + 9, 12) + 2, 5) + gd - 34840408
  d = d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752
  return d
}

function d2g(jdn: number): { gy: number; gm: number; gd: number } {
  let j = 4 * jdn + 139361631
  j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
  const i = div(mod(j, 1461), 4) * 5 + 308
  const gd = div(mod(i, 153), 5) + 1
  const gm = mod(div(i, 153), 12) + 1
  const gy = div(j, 1461) - 100100 + div(8 - gm, 6)
  return { gy, gm, gd }
}

function j2d(jy: number, jm: number, jd: number): number {
  const r = jalCal(jy)
  return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1
}

function d2j(jdn: number): { jy: number; jm: number; jd: number } {
  const gy = d2g(jdn).gy
  let jy = gy - 621
  const r = jalCal(jy)
  const jdn1f = g2d(gy, 3, r.march)
  let k = jdn - jdn1f
  if (k >= 0) {
    if (k <= 185) {
      return { jy, jm: 1 + div(k, 31), jd: mod(k, 31) + 1 }
    }
    k -= 186
  } else {
    jy -= 1
    k += 179
    if (r.leap === 1) k += 1
  }
  return { jy, jm: 7 + div(k, 30), jd: mod(k, 30) + 1 }
}

export interface JDate { jy: number; jm: number; jd: number }

export function toJalaali(gy: number, gm: number, gd: number): JDate {
  return d2j(g2d(gy, gm, gd))
}

export function toGregorian(jy: number, jm: number, jd: number): { gy: number; gm: number; gd: number } {
  return d2g(j2d(jy, jm, jd))
}

export function isLeapJalaali(jy: number): boolean {
  return jalCal(jy).leap === 0
}

export function jalaaliMonthLength(jy: number, jm: number): number {
  if (jm <= 6) return 31
  if (jm <= 11) return 30
  return isLeapJalaali(jy) ? 30 : 29
}

export const JALALI_MONTHS = [
  'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
  'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
]

export function faNum(n: number | string): string {
  return String(n).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d])
}

/** ISO (UTC) → { jy, jm, jd, hh, mm } به وقت تهران */
export function isoToJalaliParts(iso: string | null | undefined): (JDate & { hh: number; mm: number }) | null {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  const tehran = new Date(d.getTime() + 3.5 * 3600 * 1000)
  const j = toJalaali(tehran.getUTCFullYear(), tehran.getUTCMonth() + 1, tehran.getUTCDate())
  return { ...j, hh: tehran.getUTCHours(), mm: tehran.getUTCMinutes() }
}

/** {jy,jm,jd,hh,mm} به وقت تهران → ISO (UTC) */
export function jalaliPartsToIso(jy: number, jm: number, jd: number, hh = 23, mm = 59): string | null {
  try {
    const g = toGregorian(jy, jm, jd)
    const ms = Date.UTC(g.gy, g.gm - 1, g.gd, hh, mm) - 3.5 * 3600 * 1000
    return new Date(ms).toISOString()
  } catch {
    return null
  }
}

/** نمایش رشته شمسی: ۱۴۰۴/۰۷/۲۵ */
export function jalaliDisplay(iso: string | null | undefined, withTime = false): string {
  const p = isoToJalaliParts(iso)
  if (!p) return '-'
  const dateStr = `${faNum(p.jy)}/${String(p.jm).padStart(2, '0').replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d])}/${String(p.jd).padStart(2, '0').replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[+d])}`
  if (!withTime) return dateStr
  const t = `${String(p.hh).padStart(2, '0')}:${String(p.mm).padStart(2, '0')}`
  return `${dateStr} - ${faNum(t)}`
}