// تشخیص import تکراری — اجرا: npm run audit:dup
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SRC = path.resolve(__dirname, '..', 'src')

function walk(dir, out = []) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f)
    const st = fs.statSync(p)
    if (st.isDirectory()) walk(p, out)
    else if (/\.tsx?$/.test(f) && !/\.d\.ts$/.test(f)) out.push(p)
  }
  return out
}

let issues = 0
for (const file of walk(SRC)) {
  const c = fs.readFileSync(file, 'utf8')
  const ids = [...c.matchAll(/import\s*\{([^}]*)\}\s*from/g)]
    .flatMap(x => x[1].split(',').map(s => s.trim()).filter(Boolean))
  const dups = ids.filter((v, i, a) => a.indexOf(v) !== i)
  if (dups.length) {
    console.log(`[DUP] ${path.basename(file)}: ${[...new Set(dups)].join(', ')}`)
    issues++
  }
}
console.log(`\nDone. dupIssues=${issues}`)