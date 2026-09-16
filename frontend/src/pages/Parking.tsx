import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Box, Button, Card, CardContent, Chip, Stack, Tab, Tabs, Typography } from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import DirectionsCarIcon from '@mui/icons-material/DirectionsCar'
import { api } from '../api/client'
import { jalaliDisplay } from '../utils/jalali'
import CadMap, { CAD_STATUS } from '../components/CadMap'

interface Space {
  id: string; code: string; floor: number; zone?: string | null
  status: string; plate?: string | null; occupied_at?: string | null
}
interface FloorGroup { floor: number; spaces: Space[] }
interface TowerEntry {
  tower_id: string | null; code: string; name: string
  floors: FloorGroup[]; total: number; occupied: number
}
interface MapData { towers: TowerEntry[]; buried: TowerEntry | null }

const TOWER_POS: Record<string, { x: number; y: number }> = {
  'T-A': { x: 105, y: 100 },
  'T-C': { x: 555, y: 100 },
  'T-B': { x: 330, y: 330 },
}

export default function Parking() {
  const [tab, setTab] = useState(0)
  const { data } = useQuery<MapData>({
    queryKey: ['parking-map'],
    queryFn: async () => (await api.get('/parking/map')).data,
    refetchInterval: 15000,
    enabled: tab === 0 || tab === 1,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const towers = data?.towers ?? []
  const mainTowers = useMemo(
    () => Object.keys(TOWER_POS).map((c) => towers.find((t) => t.code === c)).filter((t): t is TowerEntry => !!t),
    [towers],
  )
  const otherTowers = useMemo(() => towers.filter((t) => !(t.code in TOWER_POS)), [towers])
  const buried = data?.buried ?? null
  const selected = useMemo(
    () => towers.find((t) => t.tower_id === selectedId)
      ?? (buried && buried.tower_id === selectedId ? buried : null),
    [towers, buried, selectedId],
  )
  const statusColor = (s: string) => (s === 'OCCUPIED' ? '#FB8C00' : '#2E7D32')

  const renderFloors = (entry: TowerEntry) => (
    <Stack spacing={2}>
      {entry.floors.map((f) => (
        <Card key={f.floor}>
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
              <Typography fontWeight={800}>طبقه منفی {Math.abs(f.floor)}</Typography>
              <Chip size="small" label={`${f.spaces.length} جایگاه`} variant="outlined" />
            </Stack>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 2 }}>
              {f.spaces.map((s) => (
                <Stack key={s.id} alignItems="center" spacing={1}
                  sx={{
                    borderRadius: 3, py: 2.5,
                    bgcolor: s.status === 'OCCUPIED' ? '#FFF8E1' : '#E8F5E9',
                    border: `2.5px solid ${statusColor(s.status)}`,
                  }}>
                  <Typography fontWeight={900} fontSize={17}>{s.code}</Typography>
                  {s.status === 'OCCUPIED' ? (
                    <>
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <DirectionsCarIcon sx={{ fontSize: 18, color: '#FB8C00' }} />
                        <Typography fontWeight={800} fontSize={14} sx={{ direction: 'ltr' }}>{s.plate ?? '—'}</Typography>
                      </Stack>
                      <Typography variant="caption" color="text.secondary">
                        از {jalaliDisplay(s.occupied_at, true)}
                      </Typography>
                    </>
                  ) : (
                    <Typography variant="caption" color="success.main" fontWeight={700}>آزاد</Typography>
                  )}
                </Stack>
              ))}
            </Box>
          </CardContent>
        </Card>
      ))}
    </Stack>
  )

  return (
    <Stack spacing={2}>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ bgcolor: '#fff', borderRadius: 2, px: 1 }}>
        <Tab label="نمای سایت" />
        <Tab label="طبقات برج‌ها" />
        <Tab label="نقشه CAD (DXF)" />
      </Tabs>

      {/* ---------- تب ۱: نمای سایت ---------- */}
      {tab === 0 && (
        <Card>
          <CardContent>
            <Stack direction="row" justifyContent="space-between" mb={1} flexWrap="wrap" gap={1}>
              <Typography fontWeight={800}>نقشه سایت مجتمع</Typography>
              <Stack direction="row" spacing={1}>
                <Chip size="small" sx={{ bgcolor: '#E8F5E9' }} label="برج (کلیک = طبقات)" />
                <Chip size="small" sx={{ bgcolor: '#ECEFF1' }} label="پارکینگ دفنی" />
              </Stack>
            </Stack>
            <Box dir="ltr" sx={{ width: '100%', overflowX: 'auto' }}>
              <svg viewBox="0 0 900 660" style={{ width: '100%', minWidth: 640, display: 'block' }}>
                <defs>
                  <linearGradient id="towerGrad" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#C62828" />
                    <stop offset="55%" stopColor="#B71C1C" />
                    <stop offset="100%" stopColor="#8E0000" />
                  </linearGradient>
                  <pattern id="hatch" width="8" height="8" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
                    <rect width="8" height="8" fill="#ECEFF1" />
                    <line x1="0" y1="0" x2="0" y2="8" stroke="#B0BEC5" strokeWidth="2" />
                  </pattern>
                </defs>
                <rect x="0" y="0" width="900" height="660" fill="#F4F6F8" />
                <path d="M 55 60 L 845 60 L 845 505 L 470 615 L 90 545 Z"
                  fill="none" stroke="#CFD8DC" strokeWidth="26" strokeLinejoin="round" />
                <path d="M 55 60 L 845 60 L 845 505 L 470 615 L 90 545 Z"
                  fill="none" stroke="#fff" strokeWidth="3" strokeDasharray="14 12" strokeLinejoin="round" />
                <path d="M 320 60 L 320 330 M 550 60 L 550 330 M 320 330 L 560 250"
                  fill="none" stroke="#CFD8DC" strokeWidth="16" strokeLinejoin="round" />
                <g onClick={() => buried && setSelectedId(buried.tower_id)} style={{ cursor: 'pointer' }}>
                  <rect x="380" y="225" width="190" height="72" rx="10"
                    fill="url(#hatch)" stroke="#607D8B" strokeWidth="2.5" strokeDasharray="8 5" />
                  <text x="475" y="253" textAnchor="middle" fontSize="16" fontWeight="bold" fill="#37474F">پارکینگ دفنی</text>
                  <text x="475" y="278" textAnchor="middle" fontSize="13" fill="#546E7A">
                    {buried ? `${buried.occupied} اشغال از ${buried.total}` : '—'}
                  </text>
                </g>
                {mainTowers.map((t) => {
                  const pos = TOWER_POS[t.code]
                  const letter = t.code.replace('T-', '')
                  return (
                    <g key={t.tower_id} onClick={() => setSelectedId(t.tower_id)} style={{ cursor: 'pointer' }}>
                      <rect x={pos.x} y={pos.y} width="215" height="195" rx="8"
                        fill="url(#towerGrad)" stroke="#5D0000" strokeWidth="2.5" />
                      <rect x={pos.x + 14} y={pos.y + 14} width="55" height="40" rx="4" fill="rgba(255,255,255,.16)" />
                      <rect x={pos.x + 146} y={pos.y + 14} width="55" height="40" rx="4" fill="rgba(255,255,255,.16)" />
                      <text x={pos.x + 107} y={pos.y + 42} textAnchor="middle" fontSize="15" fontWeight="bold" fill="#FFCDD2">
                        BLOCK ({letter})
                      </text>
                      <text x={pos.x + 107} y={pos.y + 92} textAnchor="middle" fontSize="22" fontWeight="900" fill="#fff">
                        {t.name}
                      </text>
                      <text x={pos.x + 107} y={pos.y + 122} textAnchor="middle" fontSize="14" fill="#FFCDD2">
                        {`اشغال ${t.occupied} از ${t.total}`}
                      </text>
                      {t.floors.map((f) => {
                        const anyOcc = f.spaces.some((s) => s.status === 'OCCUPIED')
                        return (
                          <g key={f.floor}>
                            <rect x={pos.x + 40 + (f.floor === -1 ? 0 : 80)} y={pos.y + 145}
                              width="70" height="30" rx="15"
                              fill={anyOcc ? '#FB8C00' : '#2E7D32'} opacity="0.92" />
                            <text x={pos.x + 75 + (f.floor === -1 ? 0 : 80)} y={pos.y + 165}
                              textAnchor="middle" fontSize="13" fontWeight="bold" fill="#fff">
                              طبقه {f.floor}
                            </text>
                          </g>
                        )
                      })}
                    </g>
                  )
                })}
                <g>
                  <rect x="700" y="28" width="120" height="26" rx="6" fill="#1565C0" />
                  <text x="760" y="46" textAnchor="middle" fontSize="13" fontWeight="bold" fill="#fff">ورود / خروج</text>
                </g>
              </svg>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* ---------- تب ۲: طبقات ---------- */}
      {tab === 1 && (
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
            <Typography variant="h6" fontWeight={800}>
              {selected ? `پارکینگ ${selected.name}` : 'برای مشاهده طبقات، از تب «نمای سایت» برجی را انتخاب کنید'}
            </Typography>
            {selected && (
              <Button size="small" startIcon={<ArrowBackIcon />} onClick={() => { setSelectedId(null); setTab(0) }}>
                بازگشت به نقشه سایت
              </Button>
            )}
          </Stack>
          {selected ? renderFloors(selected) : null}
          {buried && selected?.tower_id !== buried.tower_id ? (
            <Stack spacing={1}>
              <Typography fontWeight={800}>پارکینگ دفنی</Typography>
              {renderFloors(buried)}
            </Stack>
          ) : null}
        </Stack>
      )}

      {/* ---------- تب ۳: CAD ---------- */}
      {tab === 2 && <CadMap />}
    </Stack>
  )
}