'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import {
  Sparkles, Save, ArrowLeft, Trash2, X, Plus, Loader2, Target, CheckCircle, List,
} from 'lucide-react'

interface IcpResult {
  industries: string[]
  job_titles: string[]
  states: string[]
  company_sizes: string[]
  rationale: string
}

interface IcpProfile {
  id: number
  name: string
  industries: string[]
  job_titles: string[]
  states: string[]
  company_sizes: string[]
  created_at: string
}

type TagField = 'industries' | 'job_titles' | 'states' | 'company_sizes'

const STEPS = [
  { label: 'Describe Business', icon: Target },
  { label: 'Review ICP', icon: Sparkles },
  { label: 'Saved Profiles', icon: List },
]

const TAG_COLORS: Record<TagField, string> = {
  industries: 'bg-purple-100 text-purple-800',
  job_titles: 'bg-blue-100 text-blue-800',
  states: 'bg-green-100 text-green-800',
  company_sizes: 'bg-orange-100 text-orange-800',
}

const TAG_LABELS: Record<TagField, string> = {
  industries: 'Industries',
  job_titles: 'Job Titles',
  states: 'States / Regions',
  company_sizes: 'Company Sizes',
}

function ReadOnlyTags({ items, color }: { items: string[]; color: string }) {
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {items.map((t) => (
        <span key={t} className={`px-2 py-0.5 rounded-full text-xs ${color}`}>{t}</span>
      ))}
    </div>
  )
}

export default function IcpWizardPage() {
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Step 1
  const [companyDescription, setCompanyDescription] = useState('')
  const [offering, setOffering] = useState('')
  const [painPoints, setPainPoints] = useState('')

  // Step 2
  const [icpResult, setIcpResult] = useState<IcpResult | null>(null)
  const [newTag, setNewTag] = useState<Record<TagField, string>>({ industries: '', job_titles: '', states: '', company_sizes: '' })
  const [profileName, setProfileName] = useState('')

  // Step 3
  const [profiles, setProfiles] = useState<IcpProfile[]>([])
  const [profilesLoading, setProfilesLoading] = useState(false)

  const fetchProfiles = async () => {
    try {
      setProfilesLoading(true)
      const res = await api.get('/icp/profiles')
      setProfiles(res.data.profiles || res.data || [])
    } catch (err: any) {
      if (err.code !== 'ERR_CANCELED') setError(err.response?.data?.detail || 'Failed to load profiles')
    } finally {
      setProfilesLoading(false)
    }
  }

  useEffect(() => { if (step === 3) fetchProfiles() }, [step])

  const handleGenerate = async () => {
    if (!companyDescription.trim() || !offering.trim()) {
      setError('Company description and offering are required')
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await api.post('/icp/generate', {
        company_description: companyDescription, offering, pain_points: painPoints,
      })
      setIcpResult(res.data)
      setProfileName('')
      setStep(2)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate ICP')
    } finally {
      setLoading(false)
    }
  }

  const removeTag = (field: TagField, value: string) => {
    if (!icpResult) return
    setIcpResult({ ...icpResult, [field]: icpResult[field].filter((t) => t !== value) })
  }

  const addTag = (field: TagField) => {
    const val = newTag[field].trim()
    if (!val || !icpResult || icpResult[field].includes(val)) return
    setIcpResult({ ...icpResult, [field]: [...icpResult[field], val] })
    setNewTag({ ...newTag, [field]: '' })
  }

  const handleSaveProfile = async () => {
    if (!profileName.trim()) { setError('Profile name is required'); return }
    if (!icpResult) return
    setLoading(true)
    setError('')
    try {
      await api.post('/icp/profiles', {
        name: profileName, industries: icpResult.industries,
        job_titles: icpResult.job_titles, states: icpResult.states, company_sizes: icpResult.company_sizes,
      })
      setSuccess('Profile saved successfully')
      setTimeout(() => { setSuccess(''); setStep(3) }, 1200)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save profile')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteProfile = async (id: number) => {
    try {
      await api.delete(`/icp/profiles/${id}`)
      setProfiles((prev) => prev.filter((p) => p.id !== id))
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete profile')
    }
  }

  const EditableTagList = ({ field }: { field: TagField }) => {
    if (!icpResult) return null
    const items = icpResult[field]
    const color = TAG_COLORS[field]
    return (
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <span key={item} className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium ${color}`}>
            {item}
            <button onClick={() => removeTag(field, item)} className="ml-1 hover:opacity-70"><X className="w-3 h-3" /></button>
          </span>
        ))}
        <div className="flex items-center gap-1">
          <input
            type="text"
            value={newTag[field]}
            onChange={(e) => setNewTag({ ...newTag, [field]: e.target.value })}
            onKeyDown={(e) => e.key === 'Enter' && addTag(field)}
            placeholder="Add..."
            className="w-24 px-2 py-1 text-sm border border-dashed border-gray-300 rounded-full focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <button onClick={() => addTag(field)} className="p-1 text-gray-400 hover:text-blue-600">
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">ICP Wizard</h1>
        <p className="text-gray-500 mt-1">Define your Ideal Customer Profile with AI assistance.</p>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center justify-center gap-2">
        {STEPS.map((s, i) => {
          const StepIcon = s.icon
          const num = i + 1
          const active = step === num
          const done = step > num
          return (
            <div key={s.label} className="flex items-center">
              {i > 0 && <div className={`w-12 h-0.5 mx-2 ${done ? 'bg-blue-600' : 'bg-gray-200'}`} />}
              <button
                onClick={() => num <= step && setStep(num)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active ? 'bg-blue-600 text-white' : done ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-400'
                }`}
              >
                {done ? <CheckCircle className="w-4 h-4" /> : <StepIcon className="w-4 h-4" />}
                {s.label}
              </button>
            </div>
          )
        })}
      </div>

      {/* Banners */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')}><X className="w-4 h-4" /></button>
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg">{success}</div>
      )}

      {/* Step 1: Describe Business */}
      {step === 1 && (
        <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-5">
          <h2 className="text-lg font-semibold text-gray-900">Describe Your Business</h2>
          {[
            { label: 'Company Description *', value: companyDescription, setter: setCompanyDescription, ph: 'e.g., We are a staffing agency specializing in healthcare and IT talent placement...' },
            { label: 'Product / Service Offering *', value: offering, setter: setOffering, ph: 'e.g., Contract and direct-hire staffing for nurses, medical assistants, and software engineers...' },
            { label: 'Pain Points Solved', value: painPoints, setter: setPainPoints, ph: 'e.g., High turnover rates, slow time-to-fill, compliance headaches...' },
          ].map((f) => (
            <div key={f.label}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{f.label}</label>
              <textarea
                value={f.value}
                onChange={(e) => f.setter(e.target.value)}
                rows={3}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder={f.ph}
              />
            </div>
          ))}
          <div className="flex justify-end">
            <button
              onClick={handleGenerate}
              disabled={loading}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {loading ? 'Generating...' : 'Generate ICP'}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Review AI-Generated ICP */}
      {step === 2 && icpResult && (
        <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-6">
          <h2 className="text-lg font-semibold text-gray-900">AI-Generated ICP</h2>
          <p className="text-sm text-gray-500">Review and edit the generated profile. Click X to remove a tag, or type to add new ones.</p>

          {(['industries', 'job_titles', 'states', 'company_sizes'] as TagField[]).map((field) => (
            <div key={field}>
              <label className="block text-sm font-medium text-gray-700 mb-2">{TAG_LABELS[field]}</label>
              <EditableTagList field={field} />
            </div>
          ))}

          {icpResult.rationale && (
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">AI Rationale</label>
              <p className="text-sm text-gray-600 whitespace-pre-line">{icpResult.rationale}</p>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Profile Name *</label>
            <input
              type="text"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              className="w-full max-w-md border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="e.g., Healthcare Staffing Q1 2026"
            />
          </div>

          <div className="flex items-center justify-between pt-2">
            <button onClick={() => setStep(1)} className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors">
              <ArrowLeft className="w-4 h-4" /> Back
            </button>
            <button onClick={handleSaveProfile} disabled={loading} className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {loading ? 'Saving...' : 'Save Profile'}
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Saved Profiles */}
      {step === 3 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Saved Profiles</h2>
            <button onClick={() => setStep(1)} className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
              <Plus className="w-4 h-4" /> New ICP
            </button>
          </div>

          {profilesLoading ? (
            <div className="flex items-center justify-center h-32"><Loader2 className="w-5 h-5 animate-spin text-gray-400" /></div>
          ) : profiles.length === 0 ? (
            <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-500">
              No saved profiles yet. Generate your first ICP to get started.
            </div>
          ) : (
            <div className="grid gap-4">
              {profiles.map((profile) => (
                <div key={profile.id} className="bg-white rounded-lg border border-gray-200 p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold text-gray-900">{profile.name}</h3>
                      <p className="text-xs text-gray-400 mt-0.5">Created {new Date(profile.created_at).toLocaleDateString()}</p>
                    </div>
                    <button onClick={() => handleDeleteProfile(profile.id)} className="p-1.5 text-gray-400 hover:text-red-600 transition-colors" title="Delete profile">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                    {(['industries', 'job_titles', 'states', 'company_sizes'] as TagField[]).map((field) => (
                      <div key={field}>
                        <span className="text-gray-500 text-xs font-medium uppercase">{TAG_LABELS[field]}</span>
                        <ReadOnlyTags items={profile[field]} color={TAG_COLORS[field]} />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
