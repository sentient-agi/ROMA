import React, { useState, useRef } from 'react'
import { TaskGraphProvider } from '@/contexts/TaskGraphContext'
import { ThemeProvider } from '@/contexts/ThemeContext'
import MainLayout from '@/components/layout/MainLayout'
import { Toaster } from '@/components/ui/toaster'
import ErrorBoundary from '@/components/ErrorBoundary'

function App() {
  const [preview, setPreview] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  // 📌 Handle paste only inside the chat input
  const handlePaste = (event: React.ClipboardEvent<HTMLInputElement>) => {
    const items = event.clipboardData?.items
    if (!items) return

    for (const item of items) {
      if (item.type.startsWith("image/")) {
        const file = item.getAsFile()
        if (file) {
          const url = URL.createObjectURL(file)
          setPreview(url) // Show preview
          console.log("📷 Pasted image:", file)
        }
      }
    }
  }

  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="dark" storageKey="sentient-agent-theme">
        <TaskGraphProvider>
          <MainLayout />
          <Toaster />

          {/* ✅ Chat box for testing image paste */}
          <div style={{ padding: "20px" }}>
            <input
              ref={inputRef}
              type="text"
              placeholder="Paste an image here with Ctrl+V"
              onPaste={handlePaste}
              style={{
                width: "100%",
                padding: "10px",
                borderRadius: "8px",
                border: "1px solid #555",
                background: "#111",
                color: "#fff"
              }}
            />
            {preview && (
              <div style={{ marginTop: "15px" }}>
                <p style={{ color: "#ccc" }}>Preview:</p>
                <img
                  src={preview}
                  alt="pasted"
                  style={{ maxWidth: "300px", borderRadius: "8px" }}
                />
              </div>
            )}
          </div>
        </TaskGraphProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}

export default App
