import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900">
      <div className="text-center p-8">
        <h2 className="text-4xl font-bold text-gray-900 dark:text-gray-100 mb-2">404</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-6">Page not found</p>
        <Link
          href="/dashboard"
          className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          Go to Dashboard
        </Link>
      </div>
    </div>
  )
}
