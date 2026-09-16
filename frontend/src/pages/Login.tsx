import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Box, Button, Card, CardContent, Stack, TextField, Typography } from '@mui/material'
import LocalParkingIcon from '@mui/icons-material/LocalParking'
import { useAuth } from '../auth/AuthContext'
import { apiErrorFa } from '../api/client'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('Admin@1234')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      nav('/')
    } catch (err) {
      setError(apiErrorFa(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box sx={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(160deg, #0D47A1 0%, #1976D2 55%, #00897B 100%)',
    }}>
      <Card sx={{ width: 400, mx: 2 }}>
        <CardContent sx={{ p: 5 }}>
          <Stack alignItems="center" mb={3}>
            <Box sx={{
              width: 76, height: 76, borderRadius: '24px',
              background: 'linear-gradient(135deg, #1565C0, #1E88E5)',
              display: 'grid', placeItems: 'center', color: '#fff', mb: 2,
              boxShadow: '0 10px 24px rgba(21,101,192,.35)',
            }}>
              <LocalParkingIcon sx={{ fontSize: 40 }} />
            </Box>
            <Typography variant="h5" fontWeight={900}>سامانه مدیریت پارکینگ</Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>ورود کاربران سامانه</Typography>
          </Stack>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <form onSubmit={submit}>
            <TextField fullWidth label="نام کاربری" value={username} onChange={(e) => setUsername(e.target.value)} margin="normal" />
            <TextField fullWidth label="رمز عبور" type="password" value={password} onChange={(e) => setPassword(e.target.value)} margin="normal" />
            <Button fullWidth type="submit" variant="contained" size="large" disabled={loading}
              sx={{ mt: 3, py: 1.4, fontSize: 16 }}>
              {loading ? 'در حال ورود...' : 'ورود به سامانه'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </Box>
  )
}