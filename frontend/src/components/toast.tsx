'use client'

import { createContext, useCallback, useContext, useState } from 'react'
import * as Toast from '@radix-ui/react-toast'
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react'

type ToastType = 'success' | 'error' | 'info'

interface ToastItem {
  id: number
  type: ToastType
  title: string
  description?: string
}

interface ToastContextValue {
  toast: (type: ToastType, title: string, description?: string) => void
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} })

export function useToast() {
  return useContext(ToastContext)
}

let nextId = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const addToast = useCallback((type: ToastType, title: string, description?: string) => {
    const id = nextId++
    setToasts((prev) => [...prev, { id, type, title, description }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 4000)
  }, [])

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const icons = {
    success: <CheckCircle className="w-5 h-5 text-green-500" />,
    error: <AlertCircle className="w-5 h-5 text-red-500" />,
    info: <Info className="w-5 h-5 text-blue-500" />,
  }

  const colors = {
    success: 'border-green-200 bg-green-50',
    error: 'border-red-200 bg-red-50',
    info: 'border-blue-200 bg-blue-50',
  }

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      <Toast.Provider swipeDirection="right" duration={4000}>
        {children}
        {toasts.map((t) => (
          <Toast.Root
            key={t.id}
            className={`${colors[t.type]} border rounded-lg shadow-lg p-4 flex items-start gap-3 data-[state=open]:animate-slideIn data-[state=closed]:animate-fadeOut`}
            onOpenChange={(open) => { if (!open) removeToast(t.id) }}
          >
            {icons[t.type]}
            <div className="flex-1">
              <Toast.Title className="text-sm font-semibold text-gray-900">{t.title}</Toast.Title>
              {t.description && (
                <Toast.Description className="text-sm text-gray-600 mt-0.5">{t.description}</Toast.Description>
              )}
            </div>
            <Toast.Close className="text-gray-400 hover:text-gray-600">
              <X className="w-4 h-4" />
            </Toast.Close>
          </Toast.Root>
        ))}
        <Toast.Viewport className="fixed bottom-4 right-4 flex flex-col gap-2 w-96 max-w-[calc(100vw-2rem)] z-50" />
      </Toast.Provider>
    </ToastContext.Provider>
  )
}
