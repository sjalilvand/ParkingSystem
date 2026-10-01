import { useQuery } from '@tanstack/react-query'
import { Box, MenuItem, TextField } from '@mui/material'
import { api } from '../api/client'

interface SubModel { id: string; name: string }
interface CatalogModel { id: string; name: string; submodels?: SubModel[] }
interface CatalogBrand { id?: string; name: string; models?: CatalogModel[] }

interface Props {
  brand: string
  model: string
  onChange: (brand: string, model: string) => void
}

export default function CatalogPicker({ brand, model, onChange }: Props) {
  const { data: catalog } = useQuery({
    queryKey: ['vehicle-catalog'],
    queryFn: async () => (await api.get('/base-data/vehicle-catalog')).data as CatalogBrand[],
    staleTime: 24 * 3600 * 1000,
  })
  const brands: CatalogBrand[] = Array.isArray(catalog) ? catalog : []
  const brandObj = brands.find((b) => b.name === brand)
  const modelObj = (brandObj?.models ?? []).find(
    (m) => model === m.name || model.startsWith(m.name + ' '))
  const subVal = modelObj && model.length > modelObj.name.length ? model.slice(modelObj.name.length).trim() : ''

  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr 1fr' }, gap: 1.5 }}>
        <TextField select size="small" label="برند" value={brandObj ? brand : ''}
          onChange={(e) => {
            const b = e.target.value
            const first = brands.find((x) => x.name === b)?.models?.[0]?.name ?? ''
            onChange(b, first)
          }}>
          {brands.map((b) => <MenuItem key={b.id ?? b.name} value={b.name}>{b.name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="مدل" value={modelObj?.name ?? ''} disabled={!brandObj}
          onChange={(e) => onChange(brand, e.target.value)}>
          {(brandObj?.models ?? []).map((m) => <MenuItem key={m.id ?? m.name} value={m.name}>{m.name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="زیرمدل (اختیاری)" value={subVal} disabled={!modelObj}
          onChange={(e) => {
            const s = e.target.value
            onChange(brand, s ? `${modelObj!.name} ${s}` : (modelObj?.name ?? ''))
          }}>
          <MenuItem value="">—</MenuItem>
          {(modelObj?.submodels ?? []).map((s) => <MenuItem key={s.id ?? s.name} value={s.name}>{s.name}</MenuItem>)}
        </TextField>
      </Box>
    </Box>
  )
}