import { Box } from '@mui/material'
import { parsePlateRaw } from './PlateInput'

const FA = '۰۱۲۳۴۵۶۷۸۹'
const toFa = (s: string) => s.replace(/[0-9]/g, (d) => FA[Number(d)])

interface Props {
  plate?: string | null
  size?: 'sm' | 'md' | 'lg'
}

export default function PlateBox({ plate, size = 'md' }: Props) {
  const p = parsePlateRaw(plate ?? '')
  const hasMain = !!(p.two || p.letterFa || p.three)
  const k = size === 'lg' ? 1.32 : size === 'sm' ? 0.82 : 1

  const seg = {
    fontSize: 25 * k, fontWeight: 900, color: '#14181d', lineHeight: 1.1, px: 0.25,
  } as const

  return (
    <Box sx={{
      direction: 'ltr', display: 'inline-flex', alignItems: 'stretch',
      bgcolor: '#fff', border: `${Math.max(2, 2.6 * k)}px solid #14181d`,
      borderRadius: `${(1.6 * k).toFixed(2)}rem`, overflow: 'hidden', boxShadow: 1,
    }}>
      {/* بخش سفید اصلی */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 * k, px: 1.8 * k, py: 1 * k }}>
        {hasMain ? (
          <>
            <Box sx={seg}>{toFa(p.two)}</Box>
            <Box sx={{ ...seg, fontSize: 21 * k }}>{p.letterFa || '—'}</Box>
            <Box sx={seg}>{toFa(p.three)}</Box>
          </>
        ) : (
          <Box sx={seg}>{(plate ?? '').trim() || '—'}</Box>
        )}
      </Box>
      {/* کادر آبی کد استان */}
      <Box sx={{
        width: 54 * k, bgcolor: '#1e5bb8', color: '#fff',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        px: 0.5, py: 0.6 * k, gap: 0.3 * k,
      }}>
        <Box sx={{ display: 'flex', width: '72%', height: Math.max(4, 6 * k), borderRadius: 0.5, overflow: 'hidden' }}>
          <Box sx={{ flex: 1, bgcolor: '#239f40' }} />
          <Box sx={{ flex: 1, bgcolor: '#fff' }} />
          <Box sx={{ flex: 1, bgcolor: '#da0000' }} />
        </Box>
        {p.province && (
          <Box sx={{ fontSize: 16 * k, fontWeight: 900, lineHeight: 1.15 }}>{toFa(p.province)}</Box>
        )}
        <Box sx={{ fontSize: 7.5 * k, fontWeight: 700, letterSpacing: 0.4, textAlign: 'center', lineHeight: 1.2 }}>
          {p.province ? 'ایران' : 'I.R IRAN'}
        </Box>
      </Box>
    </Box>
  )
}