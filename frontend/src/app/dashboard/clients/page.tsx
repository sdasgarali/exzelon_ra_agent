'use client'

import { useState, useEffect } from 'react'
import { clientsApi } from '@/lib/api'

interface Client {
  client_id: number
  client_name: string
  status: string
  industry: string
  company_size: string
  location_state: string
  client_category: string
  service_count: number
  start_date: string
}

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showArchived, setShowArchived] = useState(false)

  useEffect(() => {
    fetchClients()
  }, [showArchived])

  const fetchClients = async () => {
    try {
      setLoading(true)
      const params: Record<string, any> = { limit: 50 }
      if (showArchived) params.show_archived = true
      const response = await clientsApi.list(params)
      // Handle both array and {items: [], total: N} response formats
      const clientList = Array.isArray(response) ? response : (response?.items || [])
      setClients(clientList)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch clients')
    } finally {
      setLoading(false)
    }
  }

  const getCategoryBadge = (category: string) => {
    const colors: Record<string, string> = {
      regular: 'bg-green-100 text-green-800',
      occasional: 'bg-blue-100 text-blue-800',
      prospect: 'bg-yellow-100 text-yellow-800',
      dormant: 'bg-gray-100 text-gray-800',
    }
    return colors[category] || 'bg-gray-100 text-gray-800'
  }

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      active: 'bg-green-100 text-green-800',
      inactive: 'bg-red-100 text-red-800',
      prospect: 'bg-yellow-100 text-yellow-800',
    }
    return colors[status] || 'bg-gray-100 text-gray-800'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading clients...</div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Clients</h1>
        <button className="btn-primary">
          + Add Client
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg mb-4">
          {error}
        </div>
      )}

      <div className="flex items-center gap-4 mb-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm font-medium text-gray-700">Show Archived</span>
          </label></div>
      <div className="card overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Client Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Industry
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Size
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Category
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Services
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {clients.map((client) => (
              <tr key={client.client_id} className="hover:bg-gray-50">
                <td className="px-6 py-4">
                  <div className="text-sm font-medium text-gray-900">{client.client_name}</div>
                  <div className="text-sm text-gray-500">{client.location_state || '-'}</div>
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {client.industry || '-'}
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {client.company_size || '-'}
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 text-xs rounded-full ${getStatusBadge(client.status)}`}>
                    {client.status}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 text-xs rounded-full ${getCategoryBadge(client.client_category)}`}>
                    {client.client_category}
                  </span>
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {client.service_count || 0}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {clients.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="text-gray-300 mb-4"><svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg></div>
            <h3 className="text-lg font-medium text-gray-900 mb-1">No clients found</h3>
            <p className="text-sm text-gray-500">Clients will appear here after running the lead sourcing pipeline.</p>
          </div>
        )}
      </div>
    </div>
  )
}
