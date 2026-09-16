import { useEffect, useMemo, useState } from 'react'
import { Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { Today as TodayIcon } from '@mui/icons-material'
import {
  JALALI_MONTHS, faNum, isoToJalaliParts, jalaaliMonthLength, jalaliPartsToIso, toJalaali,
} from '../utils/jalali'

interface Props {
  value: string | null
  onChange: (iso: string | null) => void
  label?: string
  includeTime?: boolean
}

export default function JalaliDateInput({ value, onChange, label = 'تاریخ', includeTime = true }: Props) {
  const parts = useMemo(() => isoToJalaliParts(value), [value])
  const todayJ = useMemo(() => {
    const now = new Date(Date.now() + 3.5 * 3600 * 1000)
    return toJalaali(now.getUTCFullYear(), now.getUTCMonth() + 1, now.getUTCDate())
  }, [])

  const [jy, setJy] = useState(parts?.jy ?? todayJ.jy)
  const [jm, setJm] = useState(parts?.jm ?? todayJ.jm)
  const [jd, setJd] = useState(parts?.jd ?? todayJ.jd)
  const [hh, setHh] = useState(parts?.hh ?? 23)
  const [mm, setMm] = useState(parts?.mm ?? 59)

  useEffect(() => {
    if (parts) {
      setJy(parts.jy); setJm(parts.jm); setJd(parts.jd); setHh(parts.hh); setMm(parts.mm)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const emit = (y: number, m: number, d: number, h: number, mi: number) => {
    const iso = jalaliPartsToIso(y, m, d, h, mi)
    onChange(iso)
  }

  const years = useMemo(() => {
    const list: number[] = []
    for (let y = todayJ.jy - 1; y <= todayJ.jy + 5; y++) list.push(y)
    return list
  }, [todayJ.jy])

  const maxDay = jalaaliMonthLength(jy, jm)

  return (
    <Box>
      <Typography variant="caption" color="text.secondary" mb={0.5} display="block">
        {label} (شمسی)
      </Typography>
      <Stack direction="row" spacing={1} useFlexGap>
        <TextField select size="small" label="سال" value={jy} sx={{ minWidth: 105 }}
          onChange={(e) => { const y = +e.target.value; setJy(y); emit(y, jm, Math.min(jd, jalaaliMonthLength(y, jm)), hh, mm) }}>
          {years.map((y) => <MenuItem key={y} value={y}>{faNum(y)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="ماه" value={jm} sx={{ minWidth: 110 }}
          onChange={(e) => { const m = +e.target.value; setJm(m); emit(jy, m, Math.min(jd, jalaaliMonthLength(jy, m)), hh, mm) }}>
          {JALALI_MONTHS.map((name, i) => <MenuItem key={i + 1} value={i + 1}>{name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="روز" value={jd} sx={{ minWidth: 85 }}
          onChange={(e) => { const d = +e.target.value; setJd(d); emit(jy, jm, d, hh, mm) }}>
          {Array.from({ length: maxDay }, (_, i) => i + 1).map((d) => (
            <MenuItem key={d} value={d}>{faNum(d)}</MenuItem>
          ))}
        </TextField>
        {includeTime && (
          <>
            <TextField select size="small" label="ساعت" value={hh} sx={{ minWidth: 80 }}
              onChange={(e) => { const h = +e.target.value; setHh(h); emit(jy, jm, jd, h, mm) }}>
              {Array.from({ length: 24 }, (_, i) => i).map((h) => (
                <MenuItem key={h} value={h}>{faNum(String(h).padStart(2, '0'))}</MenuItem>
              ))}
            </TextField>
            <TextField select size="small" label="دقیقه" value={mm} sx={{ minWidth: 80 }}
              onChange={(e) => { const mi = +e.target.value; setMm(mi); emit(jy, jm, jd, hh, mi) }}>
              {[0, 15, 30, 45, 59].map((mi) => (
                <MenuItem key={mi} value={mi}>{faNum(String(mi).padStart(2, '0'))}</MenuItem>
              ))}
            </TextField>
          </>
        )}
      </Stack>
      <Button size="small" startIcon={<TodayIcon />} sx={{ mt: 0.5 }}
        onClick={() => {
          const iso = jalaliPartsToIso(todayJ.jy, todayJ.jm, todayJ.jd, 23, 59)
          setJy(todayJ.jy); setJm(todayJ.jm); setJd(todayJ.jd); setHh(23); setMm(59)
          onChange(iso)
        }}>
        امروز (پایان روز)
      </Button>
    </Box>
  )
}