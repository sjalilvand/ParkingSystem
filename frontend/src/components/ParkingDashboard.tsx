import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Box, Card, CardContent, LinearProgress, Stack, Typography } from '@mui/material'
import DirectionsCarIcon from '@mui/icons-material/DirectionsCar'
import EventBusyIcon from '@mui/icons-material/EventBusy'
import BuildIcon from '@mui/icons-material/Build'
import LocalParkingIcon from '@mui/icons-material/LocalParking'
import EventSeatIcon from '@mui/icons-material/EventSeat'
import { api } from '../api/client'

/** داشبورد یک‌نگاهی وضعیت جایگاه‌های CAD — بالای صفحهٔ پارکینگ */
export default function ParkingDashboard() {
  // کلید/تابع یکسان با CadMap → کش مشترک، یک درخواست
  const { data: spots } = useQuery({
    queryKey: ['cad-spots'],
    queryFn: async () => (await api.get('/cad-parking')).data as { id: string; status: string }[],
    refetchInterval: 15000,
  })

  const stat = useMemo(() => {
    const real = (spots ?? []).filter((s) => s.status !== 'context')
    const c = { free: 0, occupied: 0, reserved: 0, other: 0 }
    for (const s of real) {
      if (s.status === 'free') c.free++
      else if (s.status === 'occupied') c.occupied++
      else if (s.status === 'reserved') c.reserved++
      else c.other++
    }
    const total = real.length
    return { ...c, total, rate: total ? Math.round((c.occupied / total) * 100) : 0 }
  }, [spots])

  const cards = [
    { label: 'آزاد', value: stat.free, color: '#21cb83', icon: <LocalParkingIcon /> },
    { label: 'اشغال', value: stat.occupied, color: '#f35061', icon: <DirectionsCarIcon /> },
    { label: 'رزرو', value: stat.reserved, color: '#f6b73c', icon: <EventBusyIcon /> },
    { label: 'تعمیرات/غیرفعال', value: stat.other, color: '#9b7cf5', icon: <BuildIcon /> },
    { label: 'کل جایگاه‌ها', value: stat.total, color: '#546E7A', icon: <EventSeatIcon /> },
  ]

  return (
    <Card>
      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={0.5} flexWrap="wrap" gap={1}>
          <Typography fontWeight={800} fontSize={15}>وضعیت لحظه‌ای پارکینگ</Typography>
          <Typography variant="caption" color="text.secondary">
            نرخ اشغال: <Box component="b" sx={{ color: '#f35061' }}>{stat.rate}٪</Box>
          </Typography>
        </Stack>
        <LinearProgress variant="determinate" value={stat.rate} sx={{
          height: 10, borderRadius: 5, mb: 1.5, bgcolor: '#E8F5E9',
          '& .MuiLinearProgress-bar': { bgcolor: '#f35061', borderRadius: 5 },
        }} />
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(3, 1fr)', md: 'repeat(5, 1fr)' }, gap: 1.2 }}>
          {cards.map((c) => (
            <Stack key={c.label} direction="row" spacing={1.2} alignItems="center"
              sx={{
                borderRadius: 2.5, px: 1.5, py: 1,
                bgcolor: `${c.color}14`,
                borderInlineStart: `5px solid ${c.color}`,
              }}>
              <Box sx={{ color: c.color, display: 'flex' }}>{c.icon}</Box>
              <Box>
                <Typography fontWeight={900} fontSize={20} lineHeight={1.1} sx={{ fontVariantNumeric: 'tabular-nums' }}>
                  {c.value}
                </Typography>
                <Typography variant="caption" color="text.secondary" fontWeight={700}>{c.label}</Typography>
              </Box>
            </Stack>
          ))}
        </Box>
      </CardContent>
    </Card>
  )
}
