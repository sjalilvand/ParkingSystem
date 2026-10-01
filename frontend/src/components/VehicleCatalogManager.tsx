import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Card,
  CardContent, Chip, IconButton, Stack, TextField, Typography,
} from '@mui/material'
import { Add, Delete, Edit, ExpandMore } from '@mui/icons-material'
import { api, apiErrorFa } from '../api/client'

interface SubModel { id?: string; name?: string | null }
interface CatalogModel { id?: string; name?: string | null; submodels?: SubModel[] }
interface CatalogBrand { id?: string; name?: string | null; models?: CatalogModel[] }

class CatalogBoundary extends React.Component<{ children: React.ReactNode }, { err: string | null }> {
  state = { err: null as string | null }
  static getDerivedStateFromError(e: unknown) { return { err: String(e) } }
  render() {
    if (this.state.err) return <Alert severity="error">خطا در کاتالوگ: {this.state.err}</Alert>
    return this.props.children
  }
}

function ManagerInner() {
  const qc = useQueryClient()
  const [newBrand, setNewBrand] = useState('')
  const [editBrand, setEditBrand] = useState<{ id: string; name: string } | null>(null)
  const [addModel, setAddModel] = useState<{ brandId: string; name: string } | null>(null)
  const [editModel, setEditModel] = useState<{ id: string; name: string } | null>(null)
  const [addSub, setAddSub] = useState<{ modelId: string; name: string } | null>(null)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const { data: catalog } = useQuery({
    queryKey: ['vehicle-catalog'],
    queryFn: async () => (await api.get('/base-data/vehicle-catalog')).data as CatalogBrand[],
  })
  const brands = (Array.isArray(catalog) ? catalog : []).filter((b) => b && (b.name ?? '') !== '')
  const refresh = () => qc.invalidateQueries({ queryKey: ['vehicle-catalog'] })
  const run = async (fn: () => Promise<unknown>) => {
    setErr(''); setMsg('')
    try { await fn(); setMsg('انجام شد'); refresh() } catch (e) { setErr(apiErrorFa(e)) }
  }

  return (
    <Card><CardContent>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5} flexWrap="wrap" useFlexGap>
        <Typography fontWeight={800}>کاتالوگ خودرو (برند، مدل، زیرمدل)</Typography>
        <Chip size="small" label={`برندها: ${brands.length}`} variant="outlined" />
      </Stack>
      {err && <Alert severity="error" sx={{ mb: 1 }}>{err}</Alert>}
      {msg && <Alert severity="success" sx={{ mb: 1 }}>{msg}</Alert>}

      <Stack direction="row" spacing={1} mb={2} flexWrap="wrap" useFlexGap>
        <TextField size="small" label="برند جدید" value={newBrand}
          onChange={(e) => setNewBrand(e.target.value)} sx={{ width: 220 }} />
        <Button variant="contained" startIcon={<Add />} disabled={!newBrand.trim()}
          onClick={() => run(async () => {
            await api.post('/base-data/brands', { name_fa: newBrand.trim() })
            setNewBrand('')
          })}>افزودن برند</Button>
      </Stack>

      {brands.map((b) => {
        const bid = b.id ?? ''
        const bname = b.name ?? ''
        const models = (b.models ?? []).filter((m) => m && (m.name ?? '') !== '')
        return (
          <Accordion key={bid || bname}>
            <AccordionSummary expandIcon={<ExpandMore />}>
              {editBrand?.id === bid ? (
                <Stack direction="row" spacing={1} onClick={(e) => e.stopPropagation()}>
                  <TextField size="small" value={editBrand.name}
                    onChange={(e) => setEditBrand({ ...editBrand, name: e.target.value })} />
                  <IconButton color="primary" onClick={(e) => { e.stopPropagation()
                    run(async () => { await api.patch(`/base-data/brands/${bid}`, { name_fa: editBrand.name }); setEditBrand(null) }) }}>
                    ✓
                  </IconButton>
                </Stack>
              ) : (
                <Stack direction="row" spacing={1} alignItems="center">
                  <Typography fontWeight={800}>{bname}</Typography>
                  <Chip size="small" label={`${models.length} مدل`} variant="outlined" />
                </Stack>
              )}
            </AccordionSummary>
            <AccordionDetails>
              <Stack direction="row" spacing={1} mb={1.5} flexWrap="wrap" useFlexGap alignItems="center">
                {editBrand?.id === bid ? null : (
                  <IconButton size="small" onClick={() => setEditBrand({ id: bid, name: bname })}><Edit /></IconButton>
                )}
                {addModel?.brandId === bid ? (
                  <>
                    <TextField size="small" label="نام مدل" value={addModel.name} autoFocus
                      onChange={(e) => setAddModel({ ...addModel, name: e.target.value })} />
                    <Button size="small" variant="contained" onClick={() => run(async () => {
                      await api.post('/base-data/vehicle-models', { brand_name: bname, name: addModel.name })
                      setAddModel(null)
                    })}>ثبت</Button>
                    <Button size="small" onClick={() => setAddModel(null)}>لغو</Button>
                  </>
                ) : (
                  <Button size="small" startIcon={<Add />} onClick={() => setAddModel({ brandId: bid, name: '' })}>افزودن مدل</Button>
                )}
              </Stack>
              {models.map((m) => {
                const mid = m.id ?? ''
                const mname = m.name ?? ''
                const subs = (m.submodels ?? []).filter((s) => s && (s.name ?? '') !== '')
                return (
                  <Box key={mid || mname} sx={{ border: '1px solid #E3EAF2', borderRadius: 2, p: 1, mb: 1 }}>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                      {editModel?.id === mid ? (
                        <>
                          <TextField size="small" value={editModel.name}
                            onChange={(e) => setEditModel({ ...editModel, name: e.target.value })} />
                          <IconButton size="small" color="primary" onClick={() => run(async () => {
                            await api.patch(`/base-data/vehicle-models/${mid}`, { name: editModel.name }); setEditModel(null)
                          })}>✓</IconButton>
                        </>
                      ) : (
                        <Typography fontWeight={700} sx={{ minWidth: 110 }}>{mname}</Typography>
                      )}
                      <IconButton size="small" onClick={() => setEditModel({ id: mid, name: mname })}><Edit fontSize="small" /></IconButton>
                      <IconButton size="small" color="error" onClick={() => run(async () => {
                        await api.delete(`/base-data/vehicle-models/${mid}`)
                      })}><Delete fontSize="small" /></IconButton>
                    </Stack>
                    <Stack direction="row" spacing={0.6} flexWrap="wrap" useFlexGap mt={0.8} alignItems="center">
                      {subs.map((s) => (
                        <Chip key={s.id ?? s.name ?? Math.random()} size="small"
                          label={s.name ?? ''} onDelete={() => run(async () => {
                            await api.delete(`/base-data/vehicle-submodels/${s.id}`)
                          })} />
                      ))}
                      {addSub?.modelId === mid ? (
                        <>
                          <TextField size="small" value={addSub.name} autoFocus
                            onChange={(e) => setAddSub({ ...addSub, name: e.target.value })} sx={{ width: 150 }} />
                          <Button size="small" variant="contained" onClick={() => run(async () => {
                            await api.post('/base-data/vehicle-submodels', { model_id: mid, name: addSub.name })
                            setAddSub(null)
                          })}>ثبت</Button>
                          <Button size="small" onClick={() => setAddSub(null)}>لغو</Button>
                        </>
                      ) : (
                        <IconButton size="small" onClick={() => setAddSub({ modelId: mid, name: '' })}><Add fontSize="small" /></IconButton>
                      )}
                    </Stack>
                  </Box>
                )
              })}
            </AccordionDetails>
          </Accordion>
        )
      })}
    </CardContent></Card>
  )
}

export default function VehicleCatalogManager() {
  return (
    <CatalogBoundary>
      <ManagerInner />
    </CatalogBoundary>
  )
}