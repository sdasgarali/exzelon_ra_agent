'use client'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900">
      <div className="text-center p-8">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">Something went wrong</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-6">{error.message || 'An unexpected error occurred.'}</p>
        <button
          onClick={reset}
          className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          Try again
        </button>
      </div>
    </div>
  )
}
