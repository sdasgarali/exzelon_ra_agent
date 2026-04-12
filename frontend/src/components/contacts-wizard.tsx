'use client'

import React, { useState, useEffect } from 'react'
import { X, Plus, Loader2 } from 'lucide-react'
import { api, contactsApi } from '@/lib/api'

interface Contact {
  contact_id: number
  first_name: string
  last_name: string
  email: string
  title: string | null
  validation_status: string | null
  data_type: string
}

interface ContactsWizardProps {
  lead: { lead_id: number; client_name: string; job_title: string }
  onClose: () => void
  onContactAdded?: () => void
}

export function ContactsWizard({ lead, onClose, onContactAdded }: ContactsWizardProps) {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ first_name: '', last_name: '', email: '', title: '' })

  const fetchContacts = async () => {
    try {
      setLoading(true)
      const response = await api.get(`/contacts?lead_id=${lead.lead_id}`)
      setContacts(response.data.items || [])
    } catch {
      setError('Failed to fetch contacts')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchContacts()
  }, [lead.lead_id])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.first_name || !form.last_name || !form.email) return
    try {
      setSaving(true)
      setError('')
      await contactsApi.create({
        first_name: form.first_name,
        last_name: form.last_name,
        email: form.email,
        title: form.title || null,
        client_name: lead.client_name,
        data_type: 'test',
        lead_ids: [lead.lead_id],
      })
      setForm({ first_name: '', last_name: '', email: '', title: '' })
      setShowAddForm(false)
      await fetchContacts()
      onContactAdded?.()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add contact')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="px-6 py-4 border-b flex justify-between items-center">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">
              Contacts for {lead.client_name}
            </h3>
            <p className="text-sm text-gray-500">{lead.job_title}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">&times;</button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 overflow-y-auto flex-1">
          {error && (
            <div className="mb-3 p-2 bg-red-50 text-red-700 text-sm rounded">{error}</div>
          )}

          {loading ? (
            <div className="text-center py-8 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin inline mr-2" />
              Loading contacts...
            </div>
          ) : contacts.length === 0 && !showAddForm ? (
            <div className="text-center py-8 text-gray-500">
              <p className="mb-2">No contacts found for this lead.</p>
              <p className="text-sm">Run Contact Enrichment or add a test contact below.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {contacts.map((contact) => (
                <div key={contact.contact_id} className="p-4 border rounded-lg hover:bg-gray-50">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="font-medium text-gray-900">
                        {contact.first_name} {contact.last_name}
                      </div>
                      <div className="text-sm text-gray-500">{contact.title || 'No title'}</div>
                      <a href={`mailto:${contact.email}`} className="text-sm text-blue-600 hover:underline">
                        {contact.email}
                      </a>
                    </div>
                    <div className="flex gap-2">
                      <span className={`text-xs px-2 py-1 rounded-full ${
                        contact.data_type === 'test'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-blue-100 text-blue-800'
                      }`}>
                        {contact.data_type === 'test' ? 'Test' : 'Enriched'}
                      </span>
                      <span className={`text-xs px-2 py-1 rounded-full ${
                        contact.validation_status === 'valid' || contact.validation_status === 'Valid'
                          ? 'bg-green-100 text-green-800'
                          : contact.validation_status === 'invalid' || contact.validation_status === 'Invalid'
                          ? 'bg-red-100 text-red-800'
                          : 'bg-gray-100 text-gray-600'
                      }`}>
                        {contact.validation_status || 'Not validated'}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Inline Add Contact Form */}
          {showAddForm && (
            <form onSubmit={handleAdd} className="mt-4 p-4 border-2 border-dashed border-blue-200 rounded-lg bg-blue-50/30">
              <h4 className="text-sm font-medium text-gray-700 mb-3">Add Test Contact</h4>
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="First name *"
                  value={form.first_name}
                  onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))}
                  className="px-3 py-2 border rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  required
                />
                <input
                  type="text"
                  placeholder="Last name *"
                  value={form.last_name}
                  onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))}
                  className="px-3 py-2 border rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  required
                />
                <input
                  type="email"
                  placeholder="Email *"
                  value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  className="px-3 py-2 border rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  required
                />
                <input
                  type="text"
                  placeholder="Title (optional)"
                  value={form.title}
                  onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  className="px-3 py-2 border rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              <div className="mt-3 flex gap-2 justify-end">
                <button type="button" onClick={() => setShowAddForm(false)} className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800">
                  Cancel
                </button>
                <button type="submit" disabled={saving} className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1">
                  {saving && <Loader2 className="w-3 h-3 animate-spin" />}
                  Save Contact
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t bg-gray-50 flex justify-between items-center">
          <span className="text-sm text-gray-500">
            {contacts.length} contact{contacts.length !== 1 ? 's' : ''} linked to this lead
          </span>
          <div className="flex gap-2">
            {!showAddForm && (
              <button
                onClick={() => setShowAddForm(true)}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Contact
              </button>
            )}
            <button onClick={onClose} className="px-3 py-1.5 text-sm border border-gray-300 rounded-md text-gray-700 hover:bg-gray-100">
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
