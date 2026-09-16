import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Alert, Box, Button, Typography } from '@mui/material'

interface Props { children: ReactNode }
interface State { error: Error | null; info: string }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: '' }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('App crash:', error, errorInfo)
    this.setState({ info: errorInfo.componentStack ?? '' })
  }

  render() {
    if (this.state.error) {
      return (
        <Box sx={{ p: 4, maxWidth: 900, mx: 'auto', mt: 6 }}>
          <Alert severity="error">
            <Typography fontWeight={800} mb={1}>خطای غیرمنتظره در برنامه رخ داد</Typography>
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', direction: 'ltr', textAlign: 'left', mb: 2 }}>
              {this.state.error.message}
            </Typography>
            <Button variant="contained" onClick={() => window.location.assign('/')}>
              بازگشت به صفحه اصلی
            </Button>
          </Alert>
        </Box>
      )
    }
    return this.props.children
  }
}