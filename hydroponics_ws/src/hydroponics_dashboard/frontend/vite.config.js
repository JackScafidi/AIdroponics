import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import crypto from 'crypto'

// Same salt+hash as the Python backend (auth.py) — password is never stored in plain text
const AUTH_SALT = 'aidroponics_auth_salt_v1'
const PASSWORD_HASH = '0b4a4c945b77c4eb0aa2bc61ffd1b294693484d3a1092fdb886fb0fcf0143126'
const activeTokens = new Set()

function mockAuthPlugin() {
  return {
    name: 'mock-auth',
    configureServer(server) {
      // Only active in dev mode — production uses the FastAPI backend
      server.middlewares.use('/api/auth', (req, res, next) => {
        // Parse body for POST requests
        if (req.method === 'POST') {
          let body = ''
          req.on('data', chunk => { body += chunk })
          req.on('end', () => {
            try {
              const data = JSON.parse(body)
              if (req.url === '/login') {
                const hash = crypto.createHash('sha256').update(AUTH_SALT + (data.password || '')).digest('hex')
                if (hash === PASSWORD_HASH) {
                  const token = crypto.randomBytes(32).toString('hex')
                  activeTokens.add(token)
                  res.writeHead(200, { 'Content-Type': 'application/json' })
                  res.end(JSON.stringify({ authenticated: true, token }))
                } else {
                  res.writeHead(401, { 'Content-Type': 'application/json' })
                  res.end(JSON.stringify({ detail: 'Invalid password' }))
                }
              } else if (req.url === '/logout') {
                const auth = req.headers.authorization || ''
                if (auth.startsWith('Bearer ')) activeTokens.delete(auth.slice(7))
                res.writeHead(200, { 'Content-Type': 'application/json' })
                res.end(JSON.stringify({ status: 'ok' }))
              } else {
                next()
              }
            } catch {
              res.writeHead(400, { 'Content-Type': 'application/json' })
              res.end(JSON.stringify({ detail: 'Bad request' }))
            }
          })
        } else if (req.method === 'GET' && req.url === '/check') {
          const auth = req.headers.authorization || ''
          const token = auth.startsWith('Bearer ') ? auth.slice(7) : ''
          const authenticated = activeTokens.has(token)
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ authenticated }))
        } else {
          next()
        }
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), mockAuthPlugin()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
