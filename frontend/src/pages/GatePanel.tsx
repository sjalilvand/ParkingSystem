import { useState, type FormEvent } from 'react'
import {
  Alert, Box, Button, Card, CardContent, Chip, Divider, List, ListItem, ListItemText,
  Stack, TextField, Typography,
} from '@mui/material'
import { CameraAlt, PhotoCamera, Login as EntryIcon, Logout as ExitIcon, Payments } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { useLiveEvents } from '../api/ws'
import { decisionColors, decisionFa } from '../app/theme'
import PlateBox from '../components/PlateBox'
import { durationFa, faDate, money } from '../utils/format'

const GATE_API_KEY = 'gate-dev-key'

interface DecisionResult {
  access_event_id: string
  decision: string
  decision_reason: string
  barrier_action: string
  warnings?: string[]
  unit?: { tower?: string; unit_number?: string } | null
  parking?: { code?: string; zone?: string } | null
  duplicate?: boolean
  session?: {
    duration_seconds?: number
    base_amount?: number
    final_amount?: number
    payment_status?: string
  } | null
}

export default function GatePanel() {
  const [direction, setDirection] = useState<'IN' | 'OUT'>('IN')
  const [plate, setPlate] = useState('۱۲ ب ۳۴۵ ایران ۶۷')
  const [result, setResult] = useState<DecisionResult | null>(null)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [paid, setPaid] = useState(false)
  const { events, connected } = useLiveEvents(15)

  const gateCode = direction === 'IN' ? 'GATE-IN-01' : 'GATE-OUT-01'

  const send = async (e: FormEvent) => {
    e.preventDefault()
    setError(''); setMsg(''); setResult(null); setPaid(false); setBusy(true)
    try {
      const r = await api.post('/gate/events/plate-detected', {
        gate_code: gateCode, direction, plate_raw: plate,
        source_event_id: crypto.randomUUID(), confidence: 97.5,
      }, { headers: { 'X-API-Key': GATE_API_KEY } })
      setResult(r.data)
    } catch (err) {
      setError(apiErrorFa(err))
    } finally { setBusy(false) }
  }

  const openBarrier = async () => {
    if (!result) return
    setBusy(true)
    try {
      await api.post('/gate/barrier/open', {
        gate_code: gateCode, access_event_id: result.access_event_id, reason: 'OPERATOR_PANEL_OPEN',
      })
      setMsg('فرمان بازشدن راهبند ثبت و ارسال شد ✔')
    } catch (err) { setError(apiErrorFa(err)) } finally { setBusy(false) }
  }

  const payNow = async () => {
    if (!result?.session?.final_amount) return
    setBusy(true)
    try {
      const r = await api.post('/payments', {
        plate_raw: plate, amount: result.session.final_amount, reference_number: `GATE-${Date.now()}`,
      })
      setPaid(true)
      setMsg(`پرداخت ثبت شد — رسید ${r.data.reference_number}`)
    } catch (err) { setError(apiErrorFa(err)) } finally { setBusy(false) }
  }

  const color = result ? (decisionColors[result.decision] ?? '#757575') : '#90A4AE'

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
      <Card sx={{ borderTop: `6px solid ${color}` }}>
        <CardContent sx={{ p: 3 }}>
          <Stack direction="row" spacing={1} mb={2.5}>
            <Button fullWidth size="large" variant={direction === 'IN' ? 'contained' : 'outlined'}
              startIcon={<EntryIcon />} onClick={() => { setDirection('IN'); setResult(null) }}>گیت ورود</Button>
            <Button fullWidth size="large" color="secondary" variant={direction === 'OUT' ? 'contained' : 'outlined'}
              startIcon={<ExitIcon />} onClick={() => { setDirection('OUT'); setResult(null) }}>گیت خروج</Button>
          </Stack>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          {msg && <Alert severity="success" sx={{ mb: 2 }}>{msg}</Alert>}

          <form onSubmit={send}>
            <TextField fullWidth label="پلاک خودرو (ورودی دوربین)" value={plate}
              onChange={(e) => setPlate(e.target.value)} sx={{ mb: 1.5 }} />
            <Stack alignItems="center" mb={2}>
              <PlateBox plate={plate} />
            </Stack>
            <Button fullWidth size="large" variant="contained" startIcon={<CameraAlt />}
              type="submit" disabled={busy} sx={{ fontSize: 17, py: 1.5 }}>
              ارسال رویداد دوربین ({gateCode})
            </Button>
          </form>

          <Divider sx={{ my: 2 }} />
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="body2" color="text.secondary">رویدادهای زنده</Typography>
            <Chip size="small" label={connected ? 'WebSocket متصل' : 'قطع'} color={connected ? 'success' : 'default'} />
          </Stack>
          <List dense sx={{ maxHeight: 200, overflow: 'auto' }}>
            {events.map((e) => (
              <ListItem key={e.event_id} divider>
                <ListItemText
                  primary={`${e.event} — ${String((e.data as { plate?: string })?.plate ?? '')}`}
                  secondary={faDate(e.occurred_at)}
                />
              </ListItem>
            ))}
          </List>
        </CardContent>
      </Card>

      <Card sx={{ bgcolor: color, color: '#fff', minHeight: 340, display: 'flex' }}>
        <CardContent sx={{ p: 3, width: '100%', display: 'flex', flexDirection: 'column' }}>
          {!result ? (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2, opacity: 0.92 }}>
              <PhotoCamera sx={{ fontSize: 72 }} />
              <Typography variant="h6">در انتظار رویداد دوربین...</Typography>
            </Box>
          ) : (
            <>
              <Stack alignItems="center" mb={2}>
                <PlateBox plate={plate} size="lg" />
              </Stack>
              <Typography variant="h3" fontWeight={900} textAlign="center" mb={1}>
                {decisionFa[result.decision] ?? result.decision}
              </Typography>
              <Stack direction="row" spacing={1} justifyContent="center" mb={2}>
                <Chip label={`راهبند: ${result.barrier_action === 'OPEN' ? 'باز شود' : 'بسته'}`}
                  sx={{ bgcolor: 'rgba(255,255,255,.25)', color: '#fff', fontWeight: 700 }} />
                {result.duplicate && <Chip label="رویداد تکراری" sx={{ bgcolor: 'rgba(255,255,255,.25)', color: '#fff' }} />}
              </Stack>
              <Typography variant="body1" mb={0.5} textAlign="center">دلیل: {result.decision_reason}</Typography>
              {result.unit && <Typography variant="body1" mb={0.5} textAlign="center">واحد: {result.unit.tower} — واحد {result.unit.unit_number}</Typography>}
              {result.parking?.code && <Typography variant="body1" mb={0.5} textAlign="center">پارکینگ: {result.parking.code}</Typography>}

              {result.session && (
                <Box sx={{ bgcolor: 'rgba(0,0,0,.22)', borderRadius: 3, p: 2, my: 2, textAlign: 'center' }}>
                  <Typography variant="subtitle1" fontWeight={800} mb={1}>صورتحساب توقف</Typography>
                  <Typography variant="body1">مدت توقف: {durationFa(result.session.duration_seconds)}</Typography>
                  <Typography variant="h4" fontWeight={900} my={1}>{money(result.session.final_amount)}</Typography>
                  <Typography variant="body2">وضعیت: {result.session.payment_status === 'UNPAID' ? 'پرداخت‌نشده' : result.session.payment_status}</Typography>
                </Box>
              )}

              {result.warnings && result.warnings.length > 0 && (
                <Alert severity="warning" sx={{ mt: 1, bgcolor: '#fff' }}>{result.warnings.join('، ')}</Alert>
              )}

              <Stack spacing={1.5} mt={2}>
                {result.barrier_action === 'OPEN' && (
                  <Button fullWidth size="large" variant="contained"
                    sx={{ bgcolor: '#fff', color, fontSize: 17, py: 1.5 }} onClick={openBarrier} disabled={busy}>
                    تأیید و بازکردن راهبند
                  </Button>
                )}
                {result.session && result.session.payment_status === 'UNPAID' && (result.session.final_amount ?? 0) > 0 && !paid && (
                  <Button fullWidth size="large" variant="contained" color="warning" startIcon={<Payments />}
                    onClick={payNow} disabled={busy} sx={{ fontSize: 16, py: 1.5 }}>
                    ثبت پرداخت {money(result.session.final_amount)}
                  </Button>
                )}
                {paid && <Alert severity="success" sx={{ bgcolor: '#fff' }}>پرداخت انجام شد ✔</Alert>}
              </Stack>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  )
}