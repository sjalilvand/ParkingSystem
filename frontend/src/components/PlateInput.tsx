import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Box, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { api } from '../api/client'

export const PLATE_LETTERS: { fa: string }[] = [
  { fa: 'الف' }, { fa: 'ب' }, { fa: 'پ' }, { fa: 'ت' }, { fa: 'ث' }, { fa: 'ج' },
  { fa: 'د' }, { fa: 'ز' }, { fa: 'س' }, { fa: 'ص' }, { fa: 'ط' }, { fa: 'ع' }, { fa: 'ف' },
  { fa: 'ق' }, { fa: 'ک' }, { fa: 'گ' }, { fa: 'ل' }, { fa: 'م' }, { fa: 'ن' },
  { fa: 'و' }, { fa: 'هـ' }, { fa: 'ی' },
]

interface Parts { two: string; letterFa: string; three: string; province: string }

export function parsePlateRaw(raw?: string | null): Parts {
  const empty: Parts = { two: '', letterFa: '', three: '', province: '' }
  if (!raw || !raw.trim()) return empty
  const toks = raw.replace(/[.\-_/,()]/g, ' ').split(/\s+/)
    .filter((t) => t && !/^(ایران|iran|ir)$/i.test(t))
  const fa2en = (s: string) => s.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
  let two = '', letterFa = '', three = '', province = ''
  for (const tk of toks) {
    const e = fa2en(tk)
    if (!letterFa && /^[ء-ی]$/.test(tk)) { letterFa = tk; continue }
    if (!two && /^\d{2}$/.test(e)) { two = tk; continue }
    if (!three && /^\d{3}$/.test(e)) { three = tk; continue }
    if (/^\d{2}$/.test(e)) { province = tk }
  }
  return { two, letterFa, three, province }
}

interface Props {
  raw: string
  onChange: (raw: string) => void
}

export default function PlateInput({ raw, onChange }: Props) {
  const [p, setP] = useState<Parts>(() => parsePlateRaw(raw))

  // جدول پایه پلاک‌ها برای resolve خودکار استان/شهر
  const { data: regions } = useQuery({
    queryKey: ['plate-regions'],
    queryFn: async () => (await api.get('/base-data/plate-regions')).data as {
      plate_code: string; province: string; city: string; letters?: string | null
    }[],
  })

  // resolve خودکار: کد استان + حرف => استان + شهر
  const regionInfo = useMemo(() => {
    if (!p.province || !p.letterFa || !regions?.length) return null
    const rows = regions.filter((r) => r.plate_code === p.province)
    const hit = rows.find((r) => (r.letters || '').split(' ').includes(p.letterFa))
    if (hit) return { province: hit.province, city: hit.city }
    if (rows.length) return { province: rows[0].province, city: null }
    return null
  }, [p.province, p.letterFa, regions])

  useEffect(() => {
    const cur = compose(p)
    if (raw !== cur) setP(parsePlateRaw(raw))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raw])

  const compose = (v: Parts): string => {
    if (!v.two && !v.three) return ''
    const parts = [v.two, v.letterFa || 'ب', v.three].filter(Boolean)
    if (v.province) parts.push('ایران', v.province)
    return parts.join(' ')
  }

  const update = (patch: Partial<Parts>) => {
    const next = { ...p, ...patch }
    setP(next)
    onChange(compose(next))
  }

  return (
    <Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1.4fr 1fr', gap: 1 }}>
        <TextField label="دو رقم" value={p.two} placeholder="۱۲"
          onChange={(e) => {
            const digits = e.target.value.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/\D/g, '')
            update({ two: digits.slice(0, 2) })
          }} />
        <TextField select label="حرف" value={p.letterFa}
          onChange={(e) => update({ letterFa: e.target.value })}>
          {PLATE_LETTERS.map((l) => <MenuItem key={l.fa} value={l.fa}>{l.fa}</MenuItem>)}
        </TextField>
        <TextField label="سه رقم" value={p.three} placeholder="۳۴۵"
          onChange={(e) => {
            const digits = e.target.value.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/\D/g, '')
            update({ three: digits.slice(0, 3) })
          }} />
        <TextField label="کد استان" value={p.province} placeholder="۲۸"
          onChange={(e) => {
            const digits = e.target.value.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/\D/g, '')
            update({ province: digits.slice(0, 2) })
          }} />
      </Box>

      {/* نمایش خودکار استان/شهر — بدون امکان انتخاب */}
      {p.province && p.letterFa ? (
        regionInfo ? (
          <Stack direction="row" spacing={1} alignItems="center" mt={1.5} justifyContent="center">
            <Typography variant="body2" fontWeight={800} color="primary.main">
              📍 استان: {regionInfo.province}
              {regionInfo.city ? ` — شهرستان: ${regionInfo.city}` : ''}
            </Typography>
          </Stack>
        ) : (
          <Typography variant="body2" color="warning.main" mt={1.5} textAlign="center">
            ⚠️ ترکیب کد {p.province} + حرف {p.letterFa} در جدول پایه یافت نشد
          </Typography>
        )
      ) : (
        <Typography variant="caption" color="text.secondary" mt={1.5} display="block" textAlign="center">
          فرمت پلاک ایران: دو رقم + یک حرف + سه رقم + کد استان (استان/شهرستان خودکار تشخیص داده می‌شود)
        </Typography>
      )}
    </Box>
  )
}