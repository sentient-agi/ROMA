import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), '')
  
  // Check if running in Docker environment
  const isDocker = env.DOCKER_ENV === 'true'
  const backendPort = env.VITE_BACKEND_PORT || '5000'
  const backendTarget = isDocker ? `http://backend:${backendPort}` : `http://localhost:${backendPort}`

  return {
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
  }
})