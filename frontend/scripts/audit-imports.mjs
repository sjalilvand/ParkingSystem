// ممیز import های MUI — اجرا: npm run audit:imports
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SRC = path.resolve(__dirname, '..', 'src')

const KNOWN = ['Alert','AlertTitle','AppBar','Avatar','Box','Button','Card','CardActions','CardContent',
'Chip','CircularProgress','Container','CssBaseline','Dialog','DialogActions','DialogContent',
'DialogTitle','Divider','Drawer','FormControl','Grid','IconButton','InputLabel','LinearProgress',
'List','ListItem','ListItemButton','ListItemIcon','ListItemText','MenuItem','Paper','Select',
'Skeleton','Snackbar','Stack','Step','StepLabel','Stepper','Switch','Tab','Table','TableBody',
'TableCell','TableContainer','TableHead','TablePagination','TableRow','Tabs','TextField',
'Toolbar','Tooltip','Typography']

function walk(dir, out = []) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f)
    const st = fs.statSync(p)
    if (st.isDirectory()) walk(p, out)
    else if (/\.tsx?$/.test(f) && !/\.d\.ts$/.test(f)) out.push(p)
  }
  return out
}

let fixed = 0, dups = 0
for (const file of walk(SRC)) {
  let c = fs.readFileSync(file, 'utf8')
  const used = [...new Set([...c.matchAll(/<([A-Z]\w*)[\s/>]/g)].map(m => m[1]).filter(n => KNOWN.includes(n)))]
  if (!used.length) continue
  const m = c.match(/import\s*\{([^}]*)\}\s*from\s*'@mui\/material'/)
  if (!m) continue
  const current = m[1].split(',').map(s => s.trim()).filter(Boolean)
  // همه شناسه‌های import شده از هر ماژول (برای رد تداخل نام)
  const allImported = [...c.matchAll(/import\s*\{([^}]*)\}\s*from/g)]
    .flatMap(x => x[1].split(',').map(s => s.trim()).filter(Boolean))
  const missing = used.filter(u => !current.includes(u) && !allImported.includes(u))
  if (!missing.length) continue
  const all = [...new Set([...current, ...missing])].sort()
  const newImport = `import {\n  ${all.join(',\n  ')},\n} from '@mui/material'`
  c = c.slice(0, m.index) + newImport + c.slice(m.index + m[0].length)
  fs.writeFileSync(file, c, 'utf8')
  console.log(`[FIXED] ${path.basename(file)}: + ${missing.join(', ')}`)
  fixed++
}
console.log(`\nDone. fixed=${fixed}, dupIssues=${dups}`)