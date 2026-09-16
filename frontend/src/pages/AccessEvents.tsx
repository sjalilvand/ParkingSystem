import { Chip, Stack, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { decisionColors, decisionFa } from '../app/theme'
import { faDate } from '../utils/format'

const typeFa: Record<string, string> = {
  ENTRY: 'ورود', EXIT: 'خروج', MANUAL_ENTRY: 'ورود دستی', MANUAL_EXIT: 'خروج دستی',
  DENIED_ENTRY: 'رد ورود', DENIED_EXIT: 'رد خروج', BARRIER_OPEN: 'بازشدن راهبند',
}

export default function AccessEvents() {
  const { data } = useQuery({
    queryKey: ['access-events'],
    queryFn: async () => (await api.get('/reports/access-events', { params: { page_size: 50 } })).data,
    refetchInterval: 8000,
  })

  return (
    <Stack spacing={1}>
      <Typography variant="h6" mb={1}>رویدادهای تردد</Typography>
      {(data?.items ?? []).map((e: Record<string, unknown>) => (
        <Stack key={e.id as string} direction="row" justifyContent="space-between" alignItems="center"
          sx={{ bgcolor: '#fff', borderRadius: 2, p: 1.5, px: 2, border: '1px solid #E0E0E0' }}>
          <Stack>
            <Typography fontWeight={800}>{String(e.plate_normalized ?? '—')}</Typography>
            <Typography variant="caption" color="text.secondary">
              {typeFa[String(e.event_type)] ?? String(e.event_type)} — {String(e.decision_reason ?? '')} {e.offline_created ? '(آفلاین)' : ''}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="caption" color="text.secondary">{faDate(e.event_time as string)}</Typography>
            <Chip size="small" label={decisionFa[String(e.decision)] ?? String(e.decision)}
              sx={{ bgcolor: decisionColors[String(e.decision)] ?? '#757575', color: '#fff' }} />
          </Stack>
        </Stack>
      ))}
      {data?.items?.length === 0 && <Typography color="text.secondary">رویدادی ثبت نشده است.</Typography>}
    </Stack>
  )
}