import { Alert, Box, Typography } from '@mui/material'

/**
 * الحاقیه §۲ — برچسب الزامی همهٔ صفحات شبیه‌ساز و آزمون:
 * «آزمایشی ـ فاقد اعتبار مالی و عملیاتی»
 */
export default function SimBanner({ dense = false }: { dense?: boolean }) {
  return (
    <Alert
      severity="warning"
      icon={<span style={{ fontSize: dense ? 16 : 20 }}>🧪</span>}
      sx={{
        mb: 2,
        border: '2px dashed #ED6C02',
        borderRadius: 2,
        '& .MuiAlert-message': { width: '100%' },
      }}
    >
      <Box sx={{ display: 'flex', flexDirection: dense ? 'row' : 'column', gap: 0.5, alignItems: 'baseline' }}>
        <Typography fontWeight={900} color="warning.dark" fontSize={dense ? 13 : 15}>
          آزمایشی ـ فاقد اعتبار مالی و عملیاتی
        </Typography>
        {!dense && (
          <Typography variant="caption" color="text.secondary">
            محیط شبیه‌سازی روی پایگاه‌دادهٔ جداگانه اجرا می‌شود؛ هیچ دادهٔ واقعی، بدهی یا سابقهٔ عملیاتی از اینجا عبور نمی‌کند.
          </Typography>
        )}
      </Box>
    </Alert>
  )
}
