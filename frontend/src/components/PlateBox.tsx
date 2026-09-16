import { Box, Stack } from '@mui/material'

interface PlateParts { two?: string; letter?: string; three?: string; province?: string; fallback?: string }

const FA = '۰۱۲۳۴۵۶۷۸۹'
const en = (s: string) => s.replace(/[۰-۹]/g, (d) => String(FA.indexOf(d))).replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
const fa = (s: string) => s.replace(/\d/g, (d) => FA[+d])
const REV: Record<string, string> = { B: 'ب', P: 'پ', D: 'د', S: 'س', T: 'ت', J: 'ج', C: 'چ', H: 'ه', X: 'خ', R: 'ر', Z: 'ز', F: 'ف', V: 'و', N: 'ن', M: 'م', L: 'ل', K: 'ک', G: 'ق', A: 'ع', Y: 'ی' }

export function parsePlate(raw?: string | null): PlateParts {
  if (!raw || !raw.trim()) return { fallback: '' }
  const toks = raw.replace(/[.\-_/\\(),]/g, ' ').split(/\s+/).filter(Boolean)
    .filter((x) => !/^(ایران|iran|ir)$/i.test(x))
  let two: string | undefined, letter: string | undefined, three: string | undefined, prov: string | undefined
  for (const tk of toks) {
    const e = en(tk)
    if (!letter && /^[ء-ی]$/.test(tk)) { letter = tk; continue }
    if (!two && /^\d{2}$/.test(e)) { two = tk; continue }
    if (!three && /^\d{3}$/.test(e)) { three = tk; continue }
    if (/^\d{2}$/.test(e)) prov = tk
  }
  if (two && letter && three) return { two, letter, three, province: prov }
  const m = en(raw).match(/(\d{2})([A-Za-z]+)(\d{3})(?:IR)?(\d{2})?/)
  if (m) return { two: fa(m[1]), letter: REV[m[2][0]] ?? m[2], three: fa(m[3]), province: m[4] ? fa(m[4]) : undefined }
  return { fallback: raw }
}

export default function PlateBox({ plate, size = 'md' }: { plate?: string | null; size?: 'md' | 'lg' }) {
  const p = parsePlate(plate)
  const h = size === 'lg' ? 92 : 58
  const fz = size === 'lg' ? 44 : 26
  const pad = size === 'lg' ? 3 : 2
  return (
    <Stack direction="row" sx={{
      direction: 'ltr', height: h, width: 'fit-content', minWidth: size === 'lg' ? 290 : 190,
      bgcolor: '#fff', border: '2.5px solid #263238', borderRadius: 1.5, overflow: 'hidden',
      boxShadow: '0 3px 10px rgba(0,0,0,.18)', userSelect: 'none',
    }}>
      <Stack sx={{ width: size === 'lg' ? 44 : 30, bgcolor: '#1565C0', alignItems: 'center', justifyContent: 'space-between', py: 0.7 }}>
        <Stack spacing={0.4}>
          <Box sx={{ width: 14, height: 3, bgcolor: '#43A047' }} />
          <Box sx={{ width: 14, height: 3, bgcolor: '#fff' }} />
          <Box sx={{ width: 14, height: 3, bgcolor: '#E53935' }} />
        </Stack>
        <Box sx={{ color: '#fff', fontSize: size === 'lg' ? 11 : 8, fontWeight: 800, lineHeight: 1.2, textAlign: 'center' }}>
          I.R.<br />IRAN
        </Box>
      </Stack>
      <Stack direction="row" sx={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: size === 'lg' ? 2.5 : 1.5, px: pad, color: '#111' }}>
        {p.fallback !== undefined && p.fallback !== '' ? (
          <Box sx={{ fontSize: fz * 0.55, fontWeight: 800 }}>{p.fallback}</Box>
        ) : (
          <>
            <Box sx={{ fontSize: fz, fontWeight: 900, minWidth: size === 'lg' ? 76 : 48, textAlign: 'center' }}>{p.two ?? '—'}</Box>
            <Box sx={{ fontSize: fz, fontWeight: 900, minWidth: size === 'lg' ? 60 : 40, textAlign: 'center' }}>{p.letter ?? '—'}</Box>
            <Box sx={{ fontSize: fz, fontWeight: 900, minWidth: size === 'lg' ? 110 : 72, textAlign: 'center' }}>{p.three ?? '—'}</Box>
          </>
        )}
      </Stack>
      {/* کد استان از گوشه پلاک حذف شد — استان/شهر در مشخصات خودرو نمایش داده می‌شود */}
    </Stack>
  )
}