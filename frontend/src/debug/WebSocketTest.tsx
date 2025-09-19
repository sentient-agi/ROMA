import React, { useState, useEffect } from 'react'
import { io, Socket } from 'socket.io-client'
import { Button } from '@/components/ui/button'

const WebSocketTest: React.FC = () => {
  const [socket, setSocket] = useState<Socket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [logs, setLogs] = useState<string[]>([])

  const addLog = (message: string) => {
    const timestamp = new Date().toLocaleTimeString()
    setLogs(prev => [`[${timestamp}] ${message}`, ...prev.slice(0, 19)])
  }

  useEffect(() => {
    const newSocket = io(window.location.origin, {
      transports: ['polling'],
      autoConnect: true,
      forceNew: false,
    })

    newSocket.on('connect', () => {
      addLog('✅ Connected to WebSocket')
      setIsConnected(true)
    })

    newSocket.on('disconnect', (reason) => {
      addLog(`❌ Disconnected: ${reason}`)
      setIsConnected(false)
    })

    newSocket.on('connect_error', (error) => {
      addLog(`❌ Connection error: ${error.message}`)
    })

    newSocket.on('task_graph_update', (data) => {
      addLog(`📊 Received update: ${Object.keys(data.all_nodes || {}).length} nodes`)
    })

    setSocket(newSocket)

    return () => {
      newSocket.disconnect()
    }
  }, [])

  const testSimpleStateChange = () => {
    addLog('🖱️ Testing simple state change...')
    // Just change local state - no WebSocket events
    const randomId = Math.random().toString(36).substring(7)
    addLog(`Random state: ${randomId}`)
  }

  const testHeavyStateChange = () => {
    addLog('⚡ Testing heavy state changes...')
    for (let i = 0; i < 10; i++) {
      setTimeout(() => {
        addLog(`Heavy operation ${i + 1}/10`)
      }, i * 100)
    }
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h2 className="text-2xl font-bold mb-4">WebSocket Debug Test</h2>
      
      <div className="mb-4">
        <div className={`inline-block px-3 py-1 rounded ${isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
          {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
        </div>
      </div>

      <div className="space-x-2 mb-4">
        <Button onClick={testSimpleStateChange}>
          Test Simple State Change
        </Button>
        <Button onClick={testHeavyStateChange}>
          Test Heavy State Changes
        </Button>
      </div>

      <div className="bg-gray-100 dark:bg-gray-800 p-4 rounded-lg h-64 overflow-y-auto">
        <h3 className="font-semibold mb-2">Connection Logs:</h3>
        {logs.map((log, index) => (
          <div key={index} className="text-sm font-mono mb-1">
            {log}
          </div>
        ))}
      </div>
    </div>
  )
}

export default WebSocketTest 