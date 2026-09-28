import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, MenuItem, Stack, TextField, Typography,
} from '@mui/material'
import { PlayArrow, Stop, TouchApp } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { useLiveEvents } from '../api/ws'
import { decisionFa } from '../app/theme'
import PlateBox from '../components/PlateBox'
import { faDate } from '../utils/format'

interface SimEvent {
  time: string; gate: string; direction: 'IN' | 'OUT'; plate: string
  decision?: string; reason?: string; barrier?: string
}
interface SimStatus {
  running: boolean; events: number; entry: number; exit: number
  violations: number; interval: number; resident_ratio: number; last?: SimEvent | null
}

export default function Simulator() {
  const qc = useQueryClient()
  const [interval, setIntervalS] = useState('4')
  const [ratio, setRatio] = useState('0.6')
  const [err, setErr] = useState('')
  const { events } = useLiveEvents(30)

  const { data: st, refetch } = useQuery({
    queryKey: ['sim-status'],
    queryFn: async () => (await api.get('/simulator/status')).data as SimStatus,
    refetchInterval: 3000,
  })

  const act = async (path: string, params = '') => {
    setErr('')
    try {
      await api.post(`/simulator/${path}${params}`)
      qc.invalidateQueries({ queryKey: ['sim-status'] })
    } catch (e) { setErr(apiErrorFa(e)) }
  }

  const simEvents = events.filter((e) => e.event === 'simulator.event') as {
    event_id: string; occurred_at: string; data: unknown
  }[]

  const colorOf = (d?: string) =>
    d === 'ALLOW' || d === 'ALLOW_WITH_WARNING' ? 'success'
    : d === 'DENY' ? 'error'
    : d === 'UNKNOWN_PLATE' ? 'warning' : 'default'

  return (
    <Stack spacing={2}>
      <Typography variant="h6" fontWeight={800}>🎮 شبیه‌ساز تردد و جریمه</Typography>
      {err && <Alert severity="error">{err}</Alert>}

      {/* کنترل */}
      <Card>
        <CardContent>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }}>
            {st?.running ? (
              <Button variant="contained" color="error" startIcon={<Stop />}
                onClick={() => act('stop')}>توقف شبیه‌سازی</Button>
            ) : (
              <Button variant="contained" color="success" startIcon={<PlayArrow />}
                onClick={() => act('start', `?interval=${interval}&resident_ratio=${ratio}`)}>
                شروع شبیه‌سازی
              </Button>
            )}
            <Button variant="outlined" startIcon={<TouchApp />} onClick={() => act('tick')}>
              یک رویداد دستی
            </Button>
            <TextField size="small" select label="فاصله رویدادها (ثانیه)" value={interval}
              onChange={(e) => setIntervalS(e.target.value)} sx={{ width: 180 }}>
              {['2','4','6','10','15'].map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
            </TextField>
            <TextField size="small" select label="نسبت ساکن/مهمان" value={ratio}
              onChange={(e) => setRatio(e.target.value)} sx={{ width: 180 }}>
              <MenuItem value="0.3">۳۰٪ ساکن</MenuItem>
              <MenuItem value="0.6">۶۰٪ ساکن</MenuItem>
              <MenuItem value="0.85">۸۵٪ ساکن</MenuItem>
            </TextField>
          </Stack>
        </CardContent>
      </Card>

      {/* آمار زنده */}
      <Card>
        <CardContent>
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
            <Chip color={st?.running ? 'success' : 'default'}
              label={st?.running ? 'در حال اجرا' : 'متوقف'} />
            <Chip variant="outlined" label={`کل رویدادها: ${st?.events ?? 0}`} />
            <Chip variant="outlined" label={`ورود: ${st?.entry ?? 0}`} color="primary" />
            <Chip variant="outlined" label={`خروج: ${st?.exit ?? 0}`} color="secondary" />
            <Chip variant="outlined" label={`جریمه/ممنوع: ${st?.violations ?? 0}`} color="warning" />
          </Stack>
        </CardContent>
      </Card>

      {/* رویدادهای زنده */}
      <Card>
        <CardContent>
          <Typography fontWeight={800} mb={1}>🚦 جریان زنده ورود/خروج</Typography>
          {simEvents.length === 0 && <Typography color="text.secondary">هنوز رویدادی نیست — شروع کنید...</Typography>}
          <Stack spacing={1}>
            {simEvents.map((e) => {
              const d = e.data as SimEvent
              return (
                <Stack key={e.event_id} direction={{ xs: 'column', sm: 'row' }}
                  spacing={1.5} alignItems={{ sm: 'center' }}
                  sx={{ border: '1px solid #E3EAF2', borderRadius: 2.5, p: 1.25 }}>
                  <Chip size="small" color={d.direction === 'IN' ? 'primary' : 'secondary'}
                    label={d.direction === 'IN' ? '⬅ ورود' : 'خروج ➡'} sx={{ minWidth: 90 }} />
                  <PlateBox plate={d.plate} size="sm" />
                  <Chip size="small" color={colorOf(d.decision) as never}
                    label={decisionFa[d.decision ?? ''] ?? d.decision ?? '-'} />
                  <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                    {d.gate} — {decisionFa[d.reason ?? ''] ?? d.reason ?? ''}
                    {d.barrier === 'OPEN' ? ' — راهبند باز' : ''}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">{faDate(e.occurred_at)}</Typography>
                </Stack>
              )
            })}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  )
}