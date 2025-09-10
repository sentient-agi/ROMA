import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Check if running in Docker environment
const isDocker = process.env.DOCKER_ENV === 'true'
const backendPort = process.env.VITE_BACKEND_PORT || '5000'
const backendTarget = isDocker ? `http://backend:${backendPort}` : `http://localhost:${backendPort}`

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    host: true,
    allowedHosts: [
      'localhost',
      '.ngrok-free.app',
      '.ngrok.io',
      '.ngrok.app'
    ],
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
        secure: false,
      },
      '/socket.io': {
        target: backendTarget,
        changeOrigin: true,
        ws: true,
      }
    }
  },
}) 