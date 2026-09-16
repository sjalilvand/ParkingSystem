import { Box, Card, CardContent, Chip, List, ListItem, ListItemText, Stack, Typography } from '@mui/material'
import {
  AccountBalanceWallet, ArrowDownward, ArrowUpward, Block, DirectionsCar,
  ErrorOutline, ReportProblem, Sensors,
} from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import { useLiveEvents } from '../api/ws'
import { faDate, money } from '../utils/format'

interface Dash {
  present_vehicles: number; entries_today: number; exits_today: number; denied_today: number
  unpaid_total: number; violations_today: number; gates_online: number; gates_total: number; devices_error: number
}
interface TrafficItem { hour: number; label: string; entries: number; exits: number }

export default function Dashboard() {
  const { data } = useQuery<Dash>({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get('/reports/dashboard')).data,
    refetchInterval: 15000,
  })
  const { data: traffic } = useQuery<{ items: TrafficItem[] }>({
    queryKey: ['hourly-traffic'],
    queryFn: async () => (await api.get('/reports/hourly-traffic')).data,
    refetchInterval: 60000,
  })
  const { events, connected } = useLiveEvents()

  const cards = [
    { label: 'خودروهای حاضر', value: data?.present_vehicles, color: '#1565C0', Icon: DirectionsCar },
    { label: 'ورود امروز', value: data?.entries_today, color: '#2E7D32', Icon: ArrowDownward },
    { label: 'خروج امروز', value: data?.exits_today, color: '#00897B', Icon: ArrowUpward },
    { label: 'ردشدگان امروز', value: data?.denied_today, color: '#C62828', Icon: Block },
    { label: 'بدهی معوق', value: money(data?.unpaid_total), color: '#F57C00', Icon: AccountBalanceWallet },
    { label: 'تخلفات امروز', value: data?.violations_today, color: '#6A1B9A', Icon: ReportProblem },
    { label: 'گیت‌های آنلاین', value: `${data?.gates_online ?? 0} / ${data?.gates_total ?? 0}`, color: '#0277BD', Icon: Sensors },
    { label: 'تجهیزات خطادار', value: data?.devices_error, color: '#D84315', Icon: ErrorOutline },
  ]

  return (
    <Stack spacing={3}>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2 }}>
        {cards.map(({ label, value, color, Icon }) => (
          <Card key={label}>
            <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Box sx={{
                width: 52, height: 52, borderRadius: 3, flexShrink: 0,
                bgcolor: `${color}1A`, color, display: 'grid', placeItems: 'center',
              }}>
                <Icon fontSize="medium" />
              </Box>
              <Box>
                <Typography variant="h5" fontWeight={900} lineHeight={1.2}>{value ?? '...'}</Typography>
                <Typography variant="body2" color="text.secondary">{label}</Typography>
              </Box>
            </CardContent>
          </Card>
        ))}
      </Box>

      <Card>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
            <Typography variant="h6" fontWeight={800}>نمودار ترافیک ساعتی (امروز — به وقت تهران)</Typography>
            <Chip size="small" label="هر ۶۰ ثانیه به‌روز" />
          </Stack>
          <Box dir="ltr" sx={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={traffic?.items ?? []} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E3EAF2" />
                <XAxis dataKey="label" tick={{ fontSize: 11, fontFamily: 'Vazirmatn' }} interval={1} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={34} />
                <Tooltip
                  contentStyle={{ fontFamily: 'Vazirmatn', direction: 'rtl', borderRadius: 12 }}
                  formatter={(value: number, name: string) => [value, name === 'entries' ? 'ورود' : 'خروج']}
                  labelFormatter={(l: string) => `ساعت ${l}:00`}
                />
                <Legend
                  formatter={(v: string) => (v === 'entries' ? 'ورود' : 'خروج')}
                  wrapperStyle={{ fontFamily: 'Vazirmatn', direction: 'rtl' }}
                />
                <Bar dataKey="entries" name="entries" fill="#2E7D32" radius={[5, 5, 0, 0]} maxBarSize={22} />
                <Bar dataKey="exits" name="exits" fill="#00897B" radius={[5, 5, 0, 0]} maxBarSize={22} />
              </BarChart>
            </ResponsiveContainer>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
            <Typography variant="h6" fontWeight={800}>رویدادهای بلادرنگ</Typography>
            <Chip size="small" label={connected ? 'زنده' : 'قطع'} color={connected ? 'success' : 'default'} />
          </Stack>
          <List dense sx={{ maxHeight: 300, overflow: 'auto' }}>
            {events.length === 0 && (
              <Typography color="text.secondary" p={2}>
                هنوز رویدادی دریافت نشده — از «پنل گیت» یک رویداد ارسال کنید.
              </Typography>
            )}
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
    </Stack>
  )
}