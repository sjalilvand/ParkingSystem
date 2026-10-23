import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, CircularProgress, Divider,
  Stack, Step, StepLabel, Stepper, Tooltip, Typography,
} from '@mui/material'
import { PlayArrow, Science } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import SimBanner from '../components/SimBanner'

interface SimScenario {
  id: string
  title: string
  precondition: string
  steps: string[]
  expected: string
}

interface RunResult {
  id: string
  title: string
  outcome: 'PASS' | 'FAIL' | 'MANUAL' | 'ERROR' | 'INCONCLUSIVE'
  label: string
  duration_ms: number
  notes: string[]
  payload: Record<string, unknown>
}

const OUTCOME_FA: Record<string, string> = {
  PASS: 'موفق',
  FAIL: 'عدم تطابق',
  MANUAL: 'میدانی/دستی',
  ERROR: 'خطای اجرا',
  INCONCLUSIVE: 'نامعین',
}

const OUTCOME_COLOR: Record<string, 'success' | 'error' | 'warning' | 'info' | 'default'> = {
  PASS: 'success',
  FAIL: 'error',
  MANUAL: 'info',
  ERROR: 'error',
  INCONCLUSIVE: 'warning',
}

export default function SimScenarios() {
  const [running, setRunning] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, RunResult>>({})
  const [err, setErr] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['sim-scenarios'],
    queryFn: async () => (await api.get('/simulator/scenarios')).data as { label: string; items: SimScenario[] },
  })
  const { data: isolation } = useQuery({
    queryKey: ['sim-isolation'],
    queryFn: async () => (await api.get('/simulator/isolation')).data as {
      label: string; sim_database: string; separated_from_operational: boolean
    },
  })

  const run = async (sid: string) => {
    setRunning(sid)
    setErr('')
    try {
      const res = await api.post(`/simulator/scenarios/${sid}/run`)
      setResults((r) => ({ ...r, [sid]: res.data as RunResult }))
    } catch (e) {
      setErr(apiErrorFa(e))
    } finally {
      setRunning(null)
    }
  }

  return (
    <Box id="top">
      <SimBanner />
      <Typography variant="h5" fontWeight={900} mb={1}>
        🧪 سناریوهای الزامی آزمون — SIM-01 تا SIM-20
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        هر سناریو دارای «پیش‌شرط / مراحل / نتیجهٔ مورد انتظار» است و خروجی اجرا با برچسب
        «{data?.label ?? 'آزمایشی ـ فاقد اعتبار مالی و عملیاتی'}» همراه است. سناریوهای میدانی (SIM-20) روی تجهیز واقعی اجرا می‌شوند.
      </Typography>

      {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

      {isLoading && <CircularProgress />}

      <Stack spacing={2}>
        {(data?.items ?? []).map((s) => {
          const res = results[s.id]
          return (
            <Card key={s.id} variant="outlined" sx={{ borderRadius: 3 }}>
              <CardContent>
                <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" mb={1}>
                  <Chip label={s.id} color="primary" size="small" sx={{ fontWeight: 900 }} />
                  <Typography fontWeight={800} sx={{ flex: 1 }}>{s.title}</Typography>
                  <Button
                    variant="contained"
                    size="small"
                    startIcon={running === s.id ? <CircularProgress size={16} color="inherit" /> : <PlayArrow />}
                    disabled={running !== null}
                    onClick={() => run(s.id)}
                  >
                    {res ? 'اجرای دوباره' : 'اجرای خودکار'}
                  </Button>
                </Stack>

                <Typography variant="caption" color="text.secondary" component="div">
                  <b>پیش‌شرط:</b> {s.precondition}
                </Typography>

                <Stepper orientation="vertical" sx={{ mt: 1, '& .MuiStepLabel-label': { fontSize: 13 } }}>
                  {s.steps.map((st, i) => (
                    <Step key={i} active>
                      <StepLabel>{st}</StepLabel>
                    </Step>
                  ))}
                </Stepper>

                <Typography variant="caption" component="div" mt={1} sx={{ color: 'success.dark' }}>
                  <b>نتیجهٔ مورد انتظار:</b> {s.expected}
                </Typography>

                {res && (
                  <>
                    <Divider sx={{ my: 1.5 }} />
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                      <Chip
                        label={`نتیجه: ${OUTCOME_FA[res.outcome] ?? res.outcome}`}
                        color={OUTCOME_COLOR[res.outcome] ?? 'default'}
                        size="small"
                        sx={{ fontWeight: 800 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        مدت: {res.duration_ms}ms
                      </Typography>
                      {res.notes.map((n, i) => (
                        <Typography key={i} variant="caption" color="text.secondary">
                          • {n}
                        </Typography>
                      ))}
                    </Stack>
                    <Tooltip title="جزئیات کامل خروجی (JSON)">
                      <Box
                        component="pre"
                        sx={{
                          mt: 1, p: 1, bgcolor: '#0d1b2a', color: '#c9d6e3', borderRadius: 2,
                          fontSize: 11, overflow: 'auto', maxHeight: 260, direction: 'ltr',
                        }}
                      >
                        {JSON.stringify(res.payload, null, 2)}
                      </Box>
                    </Tooltip>
                  </>
                )}
              </CardContent>
            </Card>
          )
        })}
      </Stack>

      <Card id="isolation" variant="outlined" sx={{ mt: 3, borderRadius: 3, bgcolor: '#FFF8E1' }}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center">
            <Science color="warning" />
            <Typography fontWeight={900}>جداسازی محیط شبیه‌سازی</Typography>
          </Stack>
          <Typography variant="body2" mt={1}>
            وضعیت: {isolation?.separated_from_operational ? '✅ جدا از محیط عملیاتی' : '⚠️ نامشخص'}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div" sx={{ direction: 'ltr', textAlign: 'left' }}>
            SIM DB: {isolation?.sim_database ?? '—'}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div" mt={1}>
            موتور قواعد و منطق تصمیم مشترک است، اما دادهٔ خودرو/نشست/بدهی/تخلف کاملاً جدا و فاقد اعتبار مالی است.
          </Typography>
        </CardContent>
      </Card>
    </Box>
  )
}
