import { useMemo, useState } from 'react'
import {
  Box, Button, IconButton, MenuItem, Popover, Stack, TextField, Typography,
} from '@mui/material'
import { ChevronLeft, ChevronRight } from '@mui/icons-material'
import { gregorianToJalali, jalaliToGregorian } from './JalaliDateTime'

const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
  'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
const WD = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج']
const p2 = (n: number) => String(n).padStart(2, '0')

function monthLen(jy: number, jm: number): number {
  if (jm <= 6) return 31
  if (jm <= 11) return 30
  return [1, 5, 9, 13, 17, 22, 26, 30].includes(jy % 33) ? 30 : 29
}

export default function JalaliDatePicker({ label, value, onChange, required }: {
  label: string; value: string | null | undefined; onChange: (iso: string) => void; required?: boolean
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const today = useMemo(() => new Date(), [])
  const init = useMemo(() => {
    if (value) { const d = new Date(value); if (!isNaN(d.getTime())) return d }
    return today
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const ij = gregorianToJalali(init.getFullYear(), init.getMonth() + 1, init.getDate())
  const [vy, setVy] = useState(ij.jy)
  const [vm, setVm] = useState(ij.jm)
  const [hh, setHh] = useState(init.getHours())
  const [mm, setMm] = useState(Math.floor(init.getMinutes() / 5) * 5)

  const display = useMemo(() => {
    if (!value) return ''
    const d = new Date(value)
    if (isNaN(d.getTime())) return ''
    const j = gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate())
    return `${j.jy}/${p2(j.jm)}/${p2(j.jd)} ${p2(d.getHours())}:${p2(d.getMinutes())}`
  }, [value])

  const sel = useMemo(() => {
    if (!value) return null
    const d = new Date(value)
    if (isNaN(d.getTime())) return null
    return gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate())
  }, [value])

  const emit = (jy: number, jm: number, jd: number, h: number, m: number) => {
    const g = jalaliToGregorian(jy, jm, jd)
    onChange(new Date(g.gy, g.gm - 1, g.gd, h, m).toISOString())
  }

  const grid = useMemo<(number | null)[]>(() => {
    const first = jalaliToGregorian(vy, vm, 1)
    const dow = new Date(first.gy, first.gm - 1, first.gd).getDay() // 0=یکشنبه
    const cells: (number | null)[] = Array((dow + 1) % 7).fill(null) // شنبه اول هفته
    for (let d = 1; d <= monthLen(vy, vm); d++) cells.push(d)
    return cells
  }, [vy, vm])

  const nav = (dir: number) => {
    let m = vm + dir, y = vy
    if (m < 1) { m = 12; y-- }
    if (m > 12) { m = 1; y++ }
    setVm(m); setVy(y)
  }

  return (
    <>
      <TextField size="small" label={`${label} (شمسی)`} required={required} value={display}
        placeholder="انتخاب تاریخ" onClick={(e) => setAnchor(e.currentTarget)}
        InputProps={{ readOnly: true }} sx={{ minWidth: 230, cursor: 'pointer' }} />
      <Popover open={!!anchor} anchorEl={anchor} onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}>
        <Box p={1.5} width={300}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
            <IconButton size="small" onClick={() => nav(-1)}><ChevronRight /></IconButton>
            <Typography fontWeight={800}>{MONTHS[vm - 1]} {vy}</Typography>
            <IconButton size="small" onClick={() => nav(1)}><ChevronLeft /></IconButton>
          </Stack>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 0.25, textAlign: 'center' }}>
            {WD.map((w) => <Typography key={w} variant="caption" color="text.secondary">{w}</Typography>)}
            {grid.map((d, i) => d === null ? <Box key={`x${i}`} /> : (
              <Button key={d} size="small"
                variant={sel && sel.jy === vy && sel.jm === vm && sel.jd === d ? 'contained' : 'text'}
                sx={{ minWidth: 34, minHeight: 34, p: 0, fontWeight: 700 }}
                onClick={() => { emit(vy, vm, d, hh, mm); setAnchor(null) }}>
                {d}
              </Button>
            ))}
          </Box>
          <Stack direction="row" spacing={1} mt={1.5}>
            <TextField select size="small" label="ساعت" value={hh} fullWidth
              onChange={(e) => { const h = +e.target.value; setHh(h); if (sel) emit(sel.jy, sel.jm, sel.jd, h, mm) }}>
              {Array.from({ length: 24 }, (_, i) => <MenuItem key={i} value={i}>{p2(i)}</MenuItem>)}
            </TextField>
            <TextField select size="small" label="دقیقه" value={mm} fullWidth
              onChange={(e) => { const m = +e.target.value; setMm(m); if (sel) emit(sel.jy, sel.jm, sel.jd, hh, m) }}>
              {Array.from({ length: 12 }, (_, i) => <MenuItem key={i} value={i * 5}>{p2(i * 5)}</MenuItem>)}
            </TextField>
          </Stack>
          <Stack direction="row" justifyContent="space-between" mt={1}>
            <Button size="small" color="warning" onClick={() => { onChange(''); setAnchor(null) }}>پاک کردن</Button>
            <Button size="small" onClick={() => {
              const j = gregorianToJalali(today.getFullYear(), today.getMonth() + 1, today.getDate())
              setVy(j.jy); setVm(j.jm); emit(j.jy, j.jm, j.jd, hh, mm); setAnchor(null)
            }}>امروز</Button>
          </Stack>
        </Box>
      </Popover>
    </>
  )
}
