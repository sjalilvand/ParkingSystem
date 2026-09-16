import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, AppBar, Badge, Box, Button, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, Divider, Drawer, IconButton, List, ListItemButton, ListItemIcon,
  ListItemText, Popover, TextField, Toolbar, Typography,
} from '@mui/material'
import {
  AccountBalance, Apartment, ConfirmationNumber, DirectionsCar,
  Dashboard as DashIcon, LockReset, Logout, LocalParking, ManageAccounts,
  Menu as MenuIcon, Notifications, Payments, ReportProblem, ReceiptLong,
  SwapHoriz, Tour, Tune,
} from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useLiveEvents } from '../api/ws'

const DRAWER_W = 250

interface NotifItem {
  id: string
  title: string
  message?: string | null
  read_at?: string | null
  created_at?: string | null
}

const menu = [
  { label: 'داشبورد', icon: <DashIcon />, path: '/' },
  { label: 'پنل گیت', icon: <SwapHoriz />, path: '/gate' },
  { label: 'ساختار مجتمع', icon: <Apartment />, path: '/structure' },
  { label: 'مسئول محوطه', icon: <Tour />, path: '/field' },
  { label: 'خودروها', icon: <DirectionsCar />, path: '/vehicles' },
  { label: 'مجوزها', icon: <ConfirmationNumber />, path: '/permits' },
  { label: 'پارکینگ', icon: <LocalParking />, path: '/parking' },
  { label: 'تردد', icon: <ReceiptLong />, path: '/access-events' },
  { label: 'بدهی‌ها', icon: <AccountBalance />, path: '/debts' },
  { label: 'تخلفات', icon: <ReportProblem />, path: '/violations' },
  { label: 'تعرفه‌ها', icon: <Payments />, path: '/tariffs' },
  { label: 'اطلاعات پایه', icon: <Tune />, path: '/base-data' },
  { label: 'کاربران و نقش‌ها', icon: <ManageAccounts />, path: '/users' },
]

export default function MainLayout() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(true)
  const qc = useQueryClient()

  const [bellAnchor, setBellAnchor] = useState<HTMLElement | null>(null)
  const bellOpen = Boolean(bellAnchor)

  const { data: unreadData } = useQuery({
    queryKey: ['notif-unread'],
    queryFn: async () => (await api.get('/notifications/unread-count')).data as { unread: number },
    refetchInterval: 60000,
  })
  const unread = unreadData?.unread ?? 0

  const { data: listData } = useQuery({
    queryKey: ['notif-list'],
    queryFn: async () => (await api.get('/notifications', { params: { page_size: 20 } })).data as { items: NotifItem[] },
    enabled: bellOpen,
  })

  const { events } = useLiveEvents(8)
  const lastNotif = events.find((e) => e.event === 'notification.new')?.event_id
  useEffect(() => {
    if (!lastNotif) return
    qc.invalidateQueries({ queryKey: ['notif-unread'] })
    if (bellOpen) qc.invalidateQueries({ queryKey: ['notif-list'] })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastNotif])

  const markRead = async (id: string) => {
    try {
      await api.post(`/notifications/${id}/read`)
      qc.invalidateQueries({ queryKey: ['notif-unread'] })
      qc.invalidateQueries({ queryKey: ['notif-list'] })
    } catch { /* ignore */ }
  }
  const markAllRead = async () => {
    try {
      await api.post('/notifications/read-all')
      qc.invalidateQueries({ queryKey: ['notif-unread'] })
      qc.invalidateQueries({ queryKey: ['notif-list'] })
    } catch { /* ignore */ }
  }

  const [pwOpen, setPwOpen] = useState(false)
  const [cur, setCur] = useState('')
  const [nw, setNw] = useState('')
  const [pwErr, setPwErr] = useState('')
  const [pwMsg, setPwMsg] = useState('')

  if (!user) return <Navigate to="/login" replace />

  const changePw = async (e: FormEvent) => {
    e.preventDefault()
    setPwErr(''); setPwMsg('')
    if (nw.length < 8) { setPwErr('رمز جدید باید حداقل ۸ کاراکتر باشد'); return }
    try {
      await api.post('/auth/change-password', { current_password: cur, new_password: nw })
      setPwMsg('رمز عبور تغییر کرد ✔')
      setCur(''); setNw('')
    } catch (err) {
      setPwErr(apiErrorFa(err))
    }
  }

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Drawer
        variant="persistent"
        anchor="right"
        open={open}
        sx={{
          width: open ? DRAWER_W : 0,
          flexShrink: 0,
          transition: (t) => t.transitions.create('width', { duration: 200 }),
          overflow: 'hidden',
          '& .MuiDrawer-paper': {
            position: 'sticky',
            top: 0,
            height: '100vh',
            width: DRAWER_W,
            boxSizing: 'border-box',
            borderLeft: '1px solid #E3EAF2',
            bgcolor: '#fff',
            overflowX: 'hidden',
          },
        }}
      >
        <Box sx={{ px: 2, pt: 2.5, pb: 1, display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Box sx={{
            width: 40, height: 40, borderRadius: 2.5,
            background: 'linear-gradient(135deg, #1565C0, #1E88E5)',
            display: 'grid', placeItems: 'center', color: '#fff',
          }}>
            <LocalParking fontSize="small" />
          </Box>
          <Typography fontWeight={900} fontSize={15}>منوی سامانه</Typography>
        </Box>
        <List sx={{ px: 1.5 }}>
          {menu.map((m) => {
            const active = pathname === m.path
            return (
              <ListItemButton
                key={m.path}
                selected={active}
                onClick={() => nav(m.path)}
                sx={{
                  borderRadius: 2.5, mb: 0.8, py: 1.2,
                  '&.Mui-selected': {
                    bgcolor: 'primary.main', color: '#fff',
                    '&:hover': { bgcolor: 'primary.dark' },
                    '& .MuiListItemIcon-root': { color: '#fff' },
                  },
                  '& .MuiListItemIcon-root': { minWidth: 44 },
                }}
              >
                <ListItemIcon sx={{ color: active ? '#fff' : 'primary.main' }}>{m.icon}</ListItemIcon>
                <ListItemText primary={m.label} primaryTypographyProps={{ fontWeight: active ? 800 : 600 }} />
              </ListItemButton>
            )
          })}
        </List>
      </Drawer>

      <Box sx={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <AppBar position="sticky" sx={{ zIndex: 1200 }}>
          <Toolbar sx={{ gap: 2 }}>
            <IconButton color="inherit" edge="start" onClick={() => setOpen(!open)}>
              <MenuIcon />
            </IconButton>
            <Box sx={{
              width: 42, height: 42, borderRadius: 2.5, bgcolor: 'rgba(255,255,255,.16)',
              display: 'grid', placeItems: 'center', boxShadow: 'inset 0 0 0 1px rgba(255,255,255,.25)',
            }}>
              <LocalParking fontSize="medium" />
            </Box>
            <Typography variant="h6" noWrap sx={{ flexGrow: 1, fontWeight: 900, letterSpacing: 0.5 }}>
              سامانه مدیریت پارکینگ
            </Typography>
            <IconButton color="inherit" title="اعلان‌ها" onClick={(e) => setBellAnchor(e.currentTarget)}>
              <Badge badgeContent={unread} color="error" max={99}>
                <Notifications />
              </Badge>
            </IconButton>
            <IconButton color="inherit" title="تغییر رمز عبور" onClick={() => { setPwOpen(true); setPwErr(''); setPwMsg('') }}>
              <LockReset />
            </IconButton>
            <Chip label={user.full_name || user.username} size="small"
              sx={{ bgcolor: 'rgba(255,255,255,.15)', color: '#fff', fontWeight: 700 }} />
            <IconButton color="inherit" onClick={() => { logout(); nav('/login') }}>
              <Logout />
            </IconButton>
          </Toolbar>
        </AppBar>

        <Box component="main" sx={{
          flexGrow: 1, p: 3, minWidth: 0,
          bgcolor: '#F0F4F8', minHeight: 'calc(100vh - 64px)',
        }}>
          <Outlet />
        </Box>
      </Box>

      <Popover
        open={bellOpen}
        anchorEl={bellAnchor}
        onClose={() => setBellAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        sx={{ mt: 1 }}
      >
        <Box sx={{ width: 340 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" px={2} py={1.5}>
            <Typography fontWeight={800}>اعلان‌ها</Typography>
            <Button size="small" onClick={markAllRead}>همه خوانده شد</Button>
          </Stack>
          <Divider />
          <List dense sx={{ maxHeight: 380, overflow: 'auto', p: 0 }}>
            {(listData?.items ?? []).map((n) => (
              <ListItemButton key={n.id} onClick={() => markRead(n.id)}
                sx={{ bgcolor: n.read_at ? 'transparent' : 'action.hover', alignItems: 'flex-start' }}>
                <ListItemText
                  primary={n.title}
                  secondary={n.message || undefined}
                  primaryTypographyProps={{ fontWeight: n.read_at ? 600 : 800 }}
                />
              </ListItemButton>
            ))}
            {listData && listData.items.length === 0 && (
              <ListItem><ListItemText primary="اعلانی وجود ندارد" /></ListItem>
            )}
          </List>
        </Box>
      </Popover>

      <Dialog open={pwOpen} onClose={() => setPwOpen(false)}>
        <DialogTitle>تغییر رمز عبور من</DialogTitle>
        <form onSubmit={changePw}>
          <DialogContent>
            {pwErr ? <Alert severity="error" sx={{ mb: 2 }}>{pwErr}</Alert> : null}
            {pwMsg ? <Alert severity="success" sx={{ mb: 2 }}>{pwMsg}</Alert> : null}
            <TextField fullWidth type="password" label="رمز فعلی" value={cur}
              onChange={(e) => setCur(e.target.value)} margin="normal" required />
            <TextField fullWidth type="password" label="رمز جدید (حداقل ۸ کاراکتر)" value={nw}
              onChange={(e) => setNw(e.target.value)} margin="normal" required />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setPwOpen(false)}>بستن</Button>
            <Button type="submit" variant="contained">تغییر رمز</Button>
          </DialogActions>
        </form>
      </Dialog>
    </Box>
  )
}