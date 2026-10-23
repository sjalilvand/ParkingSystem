import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, AppBar, Badge, Box, Button, Chip, Collapse, Dialog, DialogActions, DialogContent,
  DialogTitle, Divider, Drawer, IconButton, List, ListItem, ListItemButton, ListItemIcon,
  ListItemText, Popover, Stack, TextField, Toolbar, Typography,
} from '@mui/material'
import {
  AccountBalance, Apartment, CameraAlt, ConfirmationNumber,
  Dashboard as DashIcon, ExpandLess, ExpandMore, FactCheck, LockReset, Logout,
  LocalParking, ManageAccounts, Menu as MenuIcon, Notifications, Payments,
  ReportProblem, ReceiptLong, Science, Settings, CloudSync, SwapHoriz, Tour, Tune,
  Troubleshoot, VideogameAsset, Rule, Verified,
} from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useLiveEvents } from '../api/ws'

const DRAWER_W = 272

interface NotifItem {
  id: string
  title: string
  message?: string | null
  read_at?: string | null
  created_at?: string | null
}

// ---------------------------------------------------------------------------
// الحاقیه §۱ — ساختار درختی منو در دو سطح اول:
//   «سامانه عملیاتی» (۱۱ گروه) / «شبیه‌ساز و آزمون سناریوها» (۹ گروه)
// پنل گیت به‌صورت دکمهٔ بزرگ و پین‌شده بالای بخش عملیاتی برای اپراتور گیت.
// ---------------------------------------------------------------------------
interface MenuItem { label: string; path: string; perm?: string; icon?: ReactNode }
interface MenuGroup { label: string; icon: ReactNode; items: MenuItem[]; perm?: string }
interface MenuSection { key: string; label: string; icon: ReactNode; groups: MenuGroup[] }

const OPS_GROUPS: MenuGroup[] = [
  {
    label: 'میز عملیات', icon: <DashIcon fontSize="small" />,
    items: [
      { label: 'داشبورد', path: '/', perm: 'dashboard.view' },
      { label: 'مرکز عملیات', path: '/ops', perm: 'ops.view' },
    ],
  },
  {
    label: 'گیت و تردد', icon: <ReceiptLong fontSize="small" />,
    items: [
      { label: 'رویدادهای تردد', path: '/access-events', perm: 'access_events.view' },
      { label: 'بازبینی پلاک', path: '/plate-review', perm: 'gate.view' },
    ],
  },
  {
    label: 'ساختار و خودرو', icon: <Apartment fontSize="small" />,
    items: [
      { label: 'ساختار مجتمع', path: '/structure', perm: 'structure.view' },
      { label: 'خودروها', path: '/vehicles', perm: 'vehicles.view' },
    ],
  },
  {
    label: 'مجوزهای تردد', icon: <ConfirmationNumber fontSize="small" />,
    items: [{ label: 'مجوزها', path: '/permits', perm: 'permits.view' }],
  },
  {
    label: 'پارکینگ و جایگاه‌ها', icon: <LocalParking fontSize="small" />,
    items: [{ label: 'پارکینگ', path: '/parking', perm: 'parking.view' }],
  },
  {
    label: 'امور مالی', icon: <AccountBalance fontSize="small" />,
    items: [
      { label: 'بدهی‌ها', path: '/debts', perm: 'finance.view' },
      { label: 'تعرفه‌ها', path: '/tariffs', perm: 'finance.view' },
    ],
  },
  {
    label: 'تخلفات', icon: <ReportProblem fontSize="small" />,
    items: [{ label: 'تخلفات', path: '/violations', perm: 'violations.view' }],
  },
  {
    label: 'اطلاعات پایه و تنظیمات', icon: <Tune fontSize="small" />,
    items: [
      { label: 'اطلاعات پایه', path: '/base-data', perm: 'base_data.view' },
      { label: 'طراح تنظیمات', path: '/designer', perm: 'settings.view' },
    ],
  },
  {
    label: 'همگام‌سازی و انطباق', icon: <CloudSync fontSize="small" />,
    items: [
      { label: 'همگام‌سازی خودروها (Sheets)', path: '/vehicle-sync', perm: 'vehicles.view' },
    ],
  },
  {
    label: 'حوزهٔ عملیات میدانی', icon: <Tour fontSize="small" />,
    items: [{ label: 'مسئول محوطه', path: '/field', perm: 'parking.view' }],
  },
  {
    label: 'کاربران و امنیت', icon: <ManageAccounts fontSize="small" />,
    items: [{ label: 'کاربران و نقش‌ها', path: '/users', perm: 'user.manage' }],
  },
]

const SIM_GROUPS: MenuGroup[] = [
  {
    label: 'محیط شبیه‌سازی', icon: <VideogameAsset fontSize="small" />,
    items: [
      { label: 'شبیه‌ساز ترافیک', path: '/simulator', perm: 'simulator.view' },
    ],
  },
  {
    label: 'سناریوهای الزامی', icon: <FactCheck fontSize="small" />,
    items: [
      { label: 'کاتالوگ SIM-01..20', path: '/sim-scenarios', perm: 'simulator.view' },
    ],
  },
  {
    label: 'سناریوی آموزشی', icon: <Science fontSize="small" />,
    items: [
      { label: 'گام‌به‌گام ۵ فاز', path: '/simulator', perm: 'simulator.view' },
    ],
  },
  {
    label: 'رویداد دستی گیت', icon: <SwapHoriz fontSize="small" />,
    items: [
      { label: 'ثبت رویداد دستی', path: '/simulator', perm: 'simulator.view' },
    ],
  },
  {
    label: 'سناریوساز', icon: <Settings fontSize="small" />,
    items: [
      { label: 'دادهٔ آزمایشی و پاکسازی', path: '/scenario', perm: 'settings.view' },
    ],
  },
  {
    label: 'آزمایش قوانین', icon: <Rule fontSize="small" />,
    items: [
      { label: 'تستر قوانین', path: '/rule-tester', perm: 'rules.view' },
    ],
  },
  {
    label: 'آزمایش پلاک‌خوان', icon: <CameraAlt fontSize="small" />,
    items: [
      { label: 'پلاک‌خوان OCR', path: '/plate-ocr' },
    ],
  },
  {
    label: 'آزمون مجوز و پلاک', icon: <Verified fontSize="small" />,
    items: [
      { label: 'بازبینی پلاک (آزمایشی)', path: '/plate-review', perm: 'gate.view' },
    ],
  },
  {
    label: 'راهنمای جداسازی', icon: <Troubleshoot fontSize="small" />,
    items: [
      { label: 'وضعیت جداسازی محیط', path: '/sim-scenarios', perm: 'simulator.view' },
    ],
  },
]

const MENU_SECTIONS: MenuSection[] = [
  { key: 'ops', label: 'سامانه عملیاتی', icon: <Troubleshoot />, groups: OPS_GROUPS },
  { key: 'sim', label: 'شبیه‌ساز و آزمون سناریوها', icon: <Science />, groups: SIM_GROUPS },
]

export default function MainLayout() {
  const { user, logout, can } = useAuth()
  const nav = useNavigate()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(true)
  const qc = useQueryClient()

  // وضعیت باز/بستهٔ گروه‌ها و بخش‌ها (پیش‌فرض: بخش عملیاتی باز، گروه‌هایش بسته — ساده برای گیت)
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({ ops: true, sim: false })
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({ 'ops:گیت و تردد': true })

  const toggleSection = (key: string) =>
    setExpandedSections((s) => ({ ...s, [key]: !s[key] }))
  const toggleGroup = (key: string) =>
    setExpandedGroups((s) => ({ ...s, [key]: !s[key] }))

  const go = (path: string) => nav(path)
  const visibleItems = (items: MenuItem[]) => items.filter((it) => !it.perm || can(it.perm))

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
            display: 'flex',
            flexDirection: 'column',
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
          <Chip size="small" variant="outlined" color="primary" label="UI ۵.۰" />
        </Box>

        {/* دکمهٔ بزرگ پنل گیت — ساده و درشت برای اپراتور گیت (الحاقیه §۱) */}
        <Box sx={{ px: 1.5, pb: 1 }}>
          <Button
            fullWidth
            variant={pathname === '/gate' ? 'contained' : 'outlined'}
            startIcon={<SwapHoriz />}
            onClick={() => go('/gate')}
            sx={{ py: 1.6, borderRadius: 2.5, fontWeight: 900, fontSize: 16 }}
          >
            پنل گیت
          </Button>
        </Box>

        <List sx={{ px: 1.5, overflowY: 'auto', flex: 1 }}>
          {MENU_SECTIONS.map((section) => {
            const groups = section.groups
              .map((g) => ({ ...g, items: visibleItems(g.items) }))
              .filter((g) => g.items.length > 0)
            if (groups.length === 0) return null
            const secOpen = !!expandedSections[section.key]
            const secActive = groups.some((g) => g.items.some((it) => it.path === pathname))
            return (
              <Box key={section.key}>
                {/* سطح اول: بخش */}
                <ListItemButton
                  onClick={() => toggleSection(section.key)}
                  sx={{
                    borderRadius: 2, mb: 0.5, py: 1.1,
                    bgcolor: secActive ? 'rgba(21,101,192,.08)' : 'transparent',
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 38, color: section.key === 'sim' ? 'warning.main' : 'primary.main' }}>
                    {section.icon}
                  </ListItemIcon>
                  <ListItemText
                    primary={section.label}
                    primaryTypographyProps={{ fontWeight: 900, fontSize: 14 }}
                  />
                  {section.key === 'sim' && (
                    <Chip size="small" color="warning" variant="outlined" label="آزمایشی" sx={{ mx: 0.5 }} />
                  )}
                  {secOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
                </ListItemButton>
                <Collapse in={secOpen} timeout="auto" unmountOnExit>
                  {/* سطح دوم: گروه‌ها */}
                  {groups.map((g) => {
                    const gkey = `${section.key}:${g.label}`
                    const gActive = g.items.some((it) => it.path === pathname)
                    const gOpen = !!expandedGroups[gkey]
                    const single = g.items.length === 1
                    return (
                      <Box key={gkey} sx={{ mr: 1.5 }}>
                        <ListItemButton
                          onClick={() => (single ? go(g.items[0].path) : toggleGroup(gkey))}
                          sx={{ borderRadius: 2, py: 0.9, mb: 0.4 }}
                        >
                          <ListItemIcon sx={{ minWidth: 34, color: gActive ? 'primary.main' : 'text.secondary' }}>
                            {g.icon}
                          </ListItemIcon>
                          <ListItemText
                            primary={g.label}
                            primaryTypographyProps={{ fontWeight: gActive ? 800 : 600, fontSize: 13 }}
                          />
                          {!single && (gOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />)}
                        </ListItemButton>
                        {!single && (
                          <Collapse in={gOpen} timeout="auto" unmountOnExit>
                            {g.items.map((it) => (
                              <ListItemButton
                                key={it.label}
                                selected={pathname === it.path}
                                onClick={() => go(it.path)}
                                sx={{
                                  borderRadius: 2, mb: 0.4, py: 0.8, mr: 1.5,
                                  '&.Mui-selected': {
                                    bgcolor: 'primary.main', color: '#fff',
                                    '&:hover': { bgcolor: 'primary.dark' },
                                    '& .MuiListItemIcon-root': { color: '#fff' },
                                  },
                                }}
                              >
                                <ListItemText
                                  primary={it.label}
                                  primaryTypographyProps={{ fontWeight: pathname === it.path ? 800 : 500, fontSize: 12.5, noWrap: true }}
                                />
                              </ListItemButton>
                            ))}
                          </Collapse>
                        )}
                      </Box>
                    )
                  })}
                  <Box sx={{ height: 6 }} />
                </Collapse>
              </Box>
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
