import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, Stack, TextField, Typography,
} from '@mui/material'
import {
  Block, CheckCircle, KeyRounded, LockOpen, ManageAccounts, PersonAdd,
} from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'
import { faDate } from '../utils/format'
import { useAuth } from '../auth/AuthContext'

interface Perm { code: string; title: string; module: string }
interface RoleDef {
  id: string; code: string; name?: string; title: string; description?: string | null
  is_active?: boolean; permissions: Perm[]; users_count: number
}
interface UserRow {
  id: string; username: string; full_name: string; mobile?: string | null
  is_active: boolean; is_locked?: boolean; failed_login_count?: number
  last_login_at?: string | null; roles: string[]
}
interface RoleEditor {
  id?: string; code: string; name: string; description: string; perms: string[]
}

export default function Users() {
  const qc = useQueryClient()
  const { can } = useAuth()
  const [search, setSearch] = useState('')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const [createOpen, setCreateOpen] = useState(false)
  const [cf, setCf] = useState<Record<string, string>>({})
  const [cRoles, setCRoles] = useState<string[]>([])

  const [rolesUser, setRolesUser] = useState<UserRow | null>(null)
  const [rSel, setRSel] = useState<string[]>([])

  const [pwUser, setPwUser] = useState<UserRow | null>(null)
  const [pwVal, setPwVal] = useState('')

  // ---- ماتریس مجوزهای نقش (REQ-08-01) ----
  const [editor, setEditor] = useState<RoleEditor | null>(null)
  const [edErr, setEdErr] = useState('')

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['users'] })
    qc.invalidateQueries({ queryKey: ['roles'] })
  }

  const { data: usersData } = useQuery({
    queryKey: ['users', search],
    queryFn: async () => (await api.get('/users', { params: { search: search || undefined, page_size: 50 } })).data,
  })
  const { data: roles } = useQuery({
    queryKey: ['roles'],
    queryFn: async () => (await api.get('/roles')).data as RoleDef[],
  })
  const { data: catalog } = useQuery({
    queryKey: ['perm-catalog'],
    queryFn: async () => (await api.get('/roles/permissions-catalog')).data as Record<string, { code: string; title: string }[]>,
    enabled: editor !== null,
  })

  const roleTitle = (code: string) => (roles ?? []).find((r) => r.code === code)?.title ?? code

  const create = useMutation({
    mutationFn: async () => (await api.post('/users', {
      username: cf.username, password: cf.password, full_name: cf.full_name,
      mobile: cf.mobile || null, role_codes: cRoles,
    })).data,
    onSuccess: () => {
      setCreateOpen(false); setCf({}); setCRoles([]); setErr(''); setMsg('کاربر ساخته شد')
      invalidate()
    },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const action = useMutation({
    mutationFn: async (p: { id: string; act: 'activate' | 'deactivate' | 'unlock' }) =>
      (await api.post(`/users/${p.id}/${p.act}`)).data,
    onSuccess: () => { setErr(''); setMsg('انجام شد'); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const resetPw = useMutation({
    mutationFn: async (p: { id: string; new_password: string }) =>
      (await api.post(`/users/${p.id}/reset-password`, { new_password: p.new_password })).data,
    onSuccess: () => { setPwUser(null); setPwVal(''); setErr(''); setMsg('رمز جدید تنظیم و نشست‌های کاربر ابطال شد'); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const assign = useMutation({
    mutationFn: async (p: { id: string; role_codes: string[] }) =>
      (await api.post(`/users/${p.id}/roles`, { role_codes: p.role_codes })).data,
    onSuccess: () => { setRolesUser(null); setErr(''); setMsg('نقش‌ها به‌روزرسانی شد'); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  // ---- ذخیره نقش (ایجاد/ویرایش مجوزها) ----
  const saveRole = useMutation({
    mutationFn: async () => {
      if (editor?.id) {
        return (await api.patch(`/roles/${editor.id}`, {
          name: editor.name, description: editor.description || null,
          permission_codes: editor.perms,
        })).data
      }
      return (await api.post('/roles', {
        code: editor?.code, name: editor?.name,
        description: editor?.description || null, permission_codes: editor?.perms ?? [],
      })).data
    },
    onSuccess: () => { setEditor(null); setEdErr(''); setMsg('نقش ذخیره شد'); invalidate() },
    onError: (e) => setEdErr(apiErrorFa(e)),
  })

  const deleteRole = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/roles/${id}`)).data,
    onSuccess: () => { setErr(''); setMsg('نقش حذف شد'); invalidate() },
    onError: (e) => setErr(apiErrorFa(e)),
  })

  const submitCreate = (e: FormEvent) => { e.preventDefault(); setErr(''); create.mutate() }

  const toggleSel = (list: string[], code: string, setList: (v: string[]) => void) => {
    setList(list.includes(code) ? list.filter((c) => c !== code) : [...list, code])
  }

  const openEditor = (r?: RoleDef) => {
    setEdErr('')
    setEditor(r ? {
      id: r.id, code: r.code, name: r.title,
      description: r.description ?? '',
      perms: r.permissions.map((p) => p.code),
    } : { code: '', name: '', description: '', perms: [] })
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Stack direction="row" spacing={1} alignItems="center">
          <ManageAccounts color="primary" />
          <Typography variant="h6" fontWeight={800}>کاربران و نقش‌ها</Typography>
        </Stack>
        <Stack direction="row" spacing={1}>
          {can('roles.create') && (
            <Button variant="outlined" onClick={() => openEditor()}>نقش جدید</Button>
          )}
          <Button variant="contained" startIcon={<PersonAdd />} onClick={() => { setErr(''); setCreateOpen(true) }}>
            کاربر جدید
          </Button>
        </Stack>
      </Stack>

      {err && <Alert severity="error">{err}</Alert>}
      {msg && <Alert severity="success">{msg}</Alert>}

      <TextField size="small" placeholder="جستجو (نام کاربری / نام / موبایل)"
        value={search} onChange={(e) => setSearch(e.target.value)} sx={{ width: 340 }} />

      {/* کاربران */}
      {(usersData?.items ?? []).map((u: UserRow) => (
        <Card key={u.id}>
          <CardContent sx={{ py: 2 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
              <Stack>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Typography fontWeight={800} fontSize={16}>{u.username}</Typography>
                  {u.is_locked ? <Chip size="small" color="error" label="قفل" /> : null}
                  <Chip size="small" color={u.is_active ? 'success' : 'default'}
                    label={u.is_active ? 'فعال' : 'غیرفعال'} />
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  {u.full_name} — {u.mobile ?? 'بدون موبایل'} — آخرین ورود: {faDate(u.last_login_at)}
                </Typography>
                <Stack direction="row" spacing={0.5} mt={0.5} flexWrap="wrap" useFlexGap>
                  {u.roles.map((rc) => <Chip key={rc} size="small" label={roleTitle(rc)} variant="outlined" />)}
                  {u.roles.length === 0 && <Typography variant="caption" color="warning.main">بدون نقش</Typography>}
                </Stack>
              </Stack>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                {u.is_active ? (
                  <Button size="small" color="warning" startIcon={<Block />}
                    onClick={() => action.mutate({ id: u.id, act: 'deactivate' })}>غیرفعال</Button>
                ) : (
                  <Button size="small" color="success" startIcon={<CheckCircle />}
                    onClick={() => action.mutate({ id: u.id, act: 'activate' })}>فعال</Button>
                )}
                {u.is_locked ? (
                  <Button size="small" color="info" startIcon={<LockOpen />}
                    onClick={() => action.mutate({ id: u.id, act: 'unlock' })}>بازکردن قفل</Button>
                ) : null}
                <Button size="small" variant="outlined" startIcon={<KeyRounded />}
                  onClick={() => { setPwUser(u); setPwVal('') }}>ریست رمز</Button>
                <Button size="small" variant="contained" onClick={() => {
                  setRolesUser(u); setRSel([...u.roles])
                }}>نقش‌ها</Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>
      ))}
      {usersData?.items?.length === 0 && <Alert severity="info">کاربری یافت نشد.</Alert>}

      {/* نقش‌ها و مجوزها */}
      <Typography variant="h6" fontWeight={800} mt={2}>نقش‌ها و مجوزها (ماتریس دسترسی)</Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
        {(roles ?? []).map((r) => (
          <Card key={r.id}>
            <CardContent sx={{ py: 2 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                <Typography fontWeight={800}>{r.title} <Typography component="span" variant="caption" color="text.secondary">({r.code})</Typography></Typography>
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <Chip size="small" label={`${r.permissions.length} مجوز`} />
                  <Chip size="small" variant="outlined" label={`${r.users_count ?? 0} کاربر`} />
                </Stack>
              </Stack>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {r.permissions.map((p) => (
                  <Chip key={p.code} size="small" variant="outlined" label={p.code} />
                ))}
                {r.permissions.length === 0 && <Typography variant="caption" color="text.secondary">بدون مجوز</Typography>}
              </Stack>
              <Stack direction="row" spacing={1} mt={1.5}>
                {can('roles.edit') && (
                  <Button size="small" variant="outlined" onClick={() => openEditor(r)}>ویرایش مجوزها</Button>
                )}
                {can('roles.delete') && r.code !== 'ADMIN' && (r.users_count ?? 0) === 0 && (
                  <Button size="small" color="error"
                    onClick={() => { if (window.confirm(`حذف نقش «${r.title}»؟`)) deleteRole.mutate(r.id) }}>
                    حذف
                  </Button>
                )}
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Box>

      {/* دیالوگ کاربر جدید */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)}>
        <DialogTitle>کاربر جدید</DialogTitle>
        <form onSubmit={submitCreate}>
          <DialogContent>
            {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
            <TextField fullWidth label="نام کاربری" value={cf.username ?? ''}
              onChange={(e) => setCf((p) => ({ ...p, username: e.target.value }))} margin="normal" required />
            <TextField fullWidth label="رمز عبور (حداقل ۸ کاراکتر)" type="password" value={cf.password ?? ''}
              onChange={(e) => setCf((p) => ({ ...p, password: e.target.value }))} margin="normal" required />
            <TextField fullWidth label="نام کامل" value={cf.full_name ?? ''}
              onChange={(e) => setCf((p) => ({ ...p, full_name: e.target.value }))} margin="normal" required />
            <TextField fullWidth label="موبایل (اختیاری)" value={cf.mobile ?? ''}
              onChange={(e) => setCf((p) => ({ ...p, mobile: e.target.value }))} margin="normal" />
            <Typography fontWeight={700} mt={2} mb={1}>نقش‌ها (کلیک کنید)</Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {(roles ?? []).map((r) => (
                <Chip key={r.code} label={r.title}
                  color={cRoles.includes(r.code) ? 'primary' : 'default'}
                  onClick={() => toggleSel(cRoles, r.code, setCRoles)} />
              ))}
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setCreateOpen(false)}>انصراف</Button>
            <Button type="submit" variant="contained" disabled={create.isPending}>ثبت</Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* دیالوگ ویرایش نقش‌های کاربر */}
      <Dialog open={rolesUser !== null} onClose={() => setRolesUser(null)}>
        <DialogTitle>نقش‌های {rolesUser?.username}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, py: 2 }}>
            {(roles ?? []).map((r) => (
              <Chip key={r.code} label={r.title}
                color={rSel.includes(r.code) ? 'primary' : 'default'}
                onClick={() => toggleSel(rSel, r.code, setRSel)} />
            ))}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRolesUser(null)}>انصراف</Button>
          <Button variant="contained" disabled={assign.isPending}
            onClick={() => rolesUser && assign.mutate({ id: rolesUser.id, role_codes: rSel })}>
            ذخیره نقش‌ها
          </Button>
        </DialogActions>
      </Dialog>

      {/* دیالوگ ریست رمز */}
      <Dialog open={pwUser !== null} onClose={() => setPwUser(null)}>
        <DialogTitle>ریست رمز {pwUser?.username}</DialogTitle>
        <DialogContent>
          <TextField fullWidth type="password" label="رمز جدید (حداقل ۸ کاراکتر)"
            value={pwVal} onChange={(e) => setPwVal(e.target.value)} margin="normal" required />
          <Typography variant="caption" color="text.secondary">
            پس از ریست، همه نشست‌های فعال این کاربر ابطال می‌شود.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPwUser(null)}>انصراف</Button>
          <Button variant="contained" color="warning" disabled={pwVal.length < 8 || resetPw.isPending}
            onClick={() => pwUser && resetPw.mutate({ id: pwUser.id, new_password: pwVal })}>
            تنظیم رمز جدید
          </Button>
        </DialogActions>
      </Dialog>

      {/* دیالوگ ماتریس مجوزهای نقش */}
      <Dialog open={editor !== null} onClose={() => setEditor(null)} maxWidth="md" fullWidth>
        <DialogTitle>{editor?.id ? `ویرایش نقش «${editor.name}»` : 'نقش جدید'}</DialogTitle>
        <DialogContent>
          {edErr && <Alert severity="error" sx={{ mb: 2 }}>{edErr}</Alert>}
          <Stack direction="row" spacing={2} mt={1}>
            <TextField size="small" label="کد (لاتین)" value={editor?.code ?? ''} required
              disabled={!!editor?.id} sx={{ width: 220 }}
              onChange={(e) => setEditor((p) => p ? { ...p, code: e.target.value } : p)} />
            <TextField size="small" label="نام نقش" value={editor?.name ?? ''} required fullWidth
              onChange={(e) => setEditor((p) => p ? { ...p, name: e.target.value } : p)} />
          </Stack>
          <TextField fullWidth size="small" label="توضیح (اختیاری)" value={editor?.description ?? ''}
            onChange={(e) => setEditor((p) => p ? { ...p, description: e.target.value } : p)} margin="normal" />
          <Typography fontWeight={700} mt={2} mb={1}>مجوزها (کلیک = انتخاب/حذف)</Typography>
          {Object.entries(catalog ?? {}).map(([module, perms]) => (
            <Box key={module} mb={2}>
              <Typography variant="caption" color="text.secondary" fontWeight={800}>{module}</Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 0.5 }}>
                {perms.map((p) => (
                  <Chip key={p.code} size="small"
                    label={`${p.code} — ${p.title}`}
                    color={(editor?.perms ?? []).includes(p.code) ? 'primary' : 'default'}
                    onClick={() => setEditor((pp) => pp ? {
                      ...pp,
                      perms: pp.perms.includes(p.code) ? pp.perms.filter((c) => c !== p.code) : [...pp.perms, p.code],
                    } : pp)} />
                ))}
              </Box>
            </Box>
          ))}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditor(null)}>انصراف</Button>
          <Button variant="contained" disabled={saveRole.isPending || !editor?.code || !editor?.name}
            onClick={() => saveRole.mutate()}>ذخیره نقش</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
