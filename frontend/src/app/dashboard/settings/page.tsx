'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { settingsApi } from '@/lib/api'
import { useAuthStore } from '@/lib/store'

interface Setting {
  key: string
  value_json: string
  type: string
  description: string
  updated_by: string
  updated_at: string
}

interface JobSourceConfig {
  job_source_provider: string
  jsearch_api_key: string
  indeed_publisher_id: string
  apollo_api_key: string  // Apollo can also be used for lead sourcing
  lead_sources: string[]  // Enabled lead sources: jsearch, apollo
  enabled_sources: string[]
  target_states: string[]
  available_job_titles: string[]  // Master list of all available titles
  target_job_titles: string[]     // Currently selected/active titles for search
  target_industries: string[]
  company_size_priority_1_max: number
  company_size_priority_2_min: number
  company_size_priority_2_max: number
  exclude_it_keywords: string[]
  exclude_staffing_keywords: string[]
}

interface AIConfig {
  ai_provider: string
  groq_api_key: string
  openai_api_key: string
  anthropic_api_key: string
  gemini_api_key: string
  ai_model: string
}

interface ContactConfig {
  contact_provider: string
  contact_providers: string[]
  apollo_api_key: string
  seamless_api_key: string
}

interface ValidationConfig {
  email_validation_provider: string
  neverbounce_api_key: string
  zerobounce_api_key: string
  hunter_api_key: string
  clearout_api_key: string
  emailable_api_key: string
  mailboxvalidator_api_key: string
  reacher_api_key: string
  reacher_base_url: string
}

interface OutreachConfig {
  email_send_mode: string
  smtp_host: string
  smtp_port: string
  smtp_user: string
  smtp_password: string
  smtp_from_email: string
  smtp_from_name: string
  m365_admin_email: string
  m365_admin_password: string
}

interface BusinessRules {
  daily_send_limit: number
  cooldown_days: number
  max_contacts_per_company_job: number
  min_salary_threshold: number
  catch_all_policy: string
  unsubscribe_footer: boolean
  category_window_days: number
  category_regular_threshold: number
  category_occasional_threshold: number
}

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
]

const DEFAULT_JOB_TITLES = [
  'HR Manager', 'HR Director', 'Recruiter', 'Talent Acquisition',
  'Operations Manager', 'Plant Manager', 'Warehouse Manager',
  'Production Supervisor', 'Logistics Manager', 'Supply Chain Manager',
  'Maintenance Manager', 'Quality Manager', 'Safety Manager',
  'Facilities Manager', 'Branch Manager', 'Regional Manager',
  'General Manager', 'Site Manager', 'Distribution Manager',
  'Manufacturing Manager', 'Engineering Manager', 'Project Manager',
  'Purchasing Manager', 'Procurement Manager', 'Inventory Manager',
  'Shipping Manager', 'Receiving Manager', 'Fleet Manager',
  'Store Manager', 'Restaurant Manager', 'Hotel Manager',
  'Construction Manager', 'Field Manager', 'Service Manager',
  'Account Manager', 'Territory Manager', 'Area Manager'
]

const TARGET_INDUSTRIES = [
  'Healthcare', 'Manufacturing', 'Logistics', 'Retail', 'BFSI',
  'Education', 'Engineering', 'Automotive', 'Construction', 'Energy',
  'Oil & Gas', 'Food & Beverage', 'Hospitality', 'Real Estate',
  'Legal', 'Insurance', 'Financial Services', 'Industrial',
  'Light Industrial', 'Heavy Industrial', 'Skilled Trades', 'Agriculture'
]

const DEFAULT_IT_EXCLUSIONS = [
  'software developer', 'software engineer', 'web developer',
  'programmer', 'coding', 'data scientist', 'devops',
  'full stack', 'frontend developer', 'backend developer',
  'cloud architect', 'cybersecurity analyst', 'network administrator',
  'machine learning engineer'
]

const DEFAULT_STAFFING_EXCLUSIONS = [
  'staffing agency', 'staffing firm', 'recruitment agency',
  'talent acquisition agency', 'temp agency',
  'employment agency', 'executive search firm'
]

export default function SettingsPage() {
  const router = useRouter()
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'

  // Only admin can access settings
  useEffect(() => {
    if (user && !isAdmin) {
      router.replace('/dashboard')
    }
  }, [user, isAdmin, router])

  const [settings, setSettings] = useState<Setting[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [isLocalhost, setIsLocalhost] = useState(false)
  const [activeTab, setActiveTab] = useState('jobsources')

  // Job Source configuration
  const [jobSourceConfig, setJobSourceConfig] = useState<JobSourceConfig>({
    job_source_provider: 'jsearch',
    jsearch_api_key: '',
    indeed_publisher_id: '',
    apollo_api_key: '',
    lead_sources: ['jsearch'],
    enabled_sources: ['linkedin', 'indeed', 'glassdoor', 'simplyhired'],
    target_states: ['CA', 'TX', 'FL', 'NY', 'IL', 'PA', 'OH', 'GA', 'NC', 'MI'],
    available_job_titles: DEFAULT_JOB_TITLES,
    target_job_titles: DEFAULT_JOB_TITLES.slice(0, 16), // First 16 selected by default
    target_industries: TARGET_INDUSTRIES,
    company_size_priority_1_max: 50,
    company_size_priority_2_min: 51,
    company_size_priority_2_max: 500,
    exclude_it_keywords: DEFAULT_IT_EXCLUSIONS,
    exclude_staffing_keywords: DEFAULT_STAFFING_EXCLUSIONS,
  })

  // State for adding new job title
  const [newJobTitle, setNewJobTitle] = useState('')

  // State for adding new exclusion keywords
  const [newITKeyword, setNewITKeyword] = useState('')
  const [newStaffingKeyword, setNewStaffingKeyword] = useState('')

  // AI configuration
  const [aiConfig, setAIConfig] = useState<AIConfig>({
    ai_provider: 'groq',
    groq_api_key: '',
    openai_api_key: '',
    anthropic_api_key: '',
    gemini_api_key: '',
    ai_model: 'llama-3.1-70b-versatile',
  })

  // Contact configuration
  const [contactConfig, setContactConfig] = useState<ContactConfig>({
    contact_provider: 'mock',
    contact_providers: ['mock'],
    apollo_api_key: '',
    seamless_api_key: '',
  })

  // Validation configuration
  const [validationConfig, setValidationConfig] = useState<ValidationConfig>({
    email_validation_provider: 'mock',
    neverbounce_api_key: '',
    zerobounce_api_key: '',
    hunter_api_key: '',
    clearout_api_key: '',
    emailable_api_key: '',
    mailboxvalidator_api_key: '',
    reacher_api_key: '',
    reacher_base_url: 'https://api.reacher.email',
  })

  // Outreach configuration
  const [outreachConfig, setOutreachConfig] = useState<OutreachConfig>({
    email_send_mode: 'mailmerge',
    smtp_host: '',
    smtp_port: '587',
    smtp_user: '',
    smtp_password: '',
    smtp_from_email: '',
    smtp_from_name: '',
    m365_admin_email: '',
    m365_admin_password: '',
  })

  // Business rules
  const [businessRules, setBusinessRules] = useState<BusinessRules>({
    daily_send_limit: 30,
    cooldown_days: 10,
    max_contacts_per_company_job: 4,
    min_salary_threshold: 40000,
    catch_all_policy: 'exclude',
    unsubscribe_footer: true,
    category_window_days: 90,
    category_regular_threshold: 3,
    category_occasional_threshold: 0,
  })

  // Test results
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message: string }>>({})

  useEffect(() => {
    fetchSettings()
  }, [])

  const fetchSettings = async () => {
    try {
      setLoading(true)
      setError('')
      const response = await settingsApi.list()
      setSettings(response || [])

      const settingsMap: Record<string, any> = {}
      for (const s of response || []) {
        try {
          settingsMap[s.key] = JSON.parse(s.value_json)
        } catch {
          settingsMap[s.key] = s.value_json
        }
      }

      // Update all configs from settings
      // Merge available titles: stored + defaults (remove duplicates)
      const storedAvailable = settingsMap.available_job_titles || []
      const mergedAvailable = Array.from(new Set([...DEFAULT_JOB_TITLES, ...storedAvailable]))

      const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
      setIsLocalhost(isLocal)

      setJobSourceConfig(prev => ({
        ...prev,
        job_source_provider: settingsMap.job_source_provider || 'jsearch',
        jsearch_api_key: settingsMap.jsearch_api_key || '',
        indeed_publisher_id: settingsMap.indeed_publisher_id || '',
        apollo_api_key: settingsMap.apollo_api_key || '',
        lead_sources: settingsMap.lead_sources || (isLocal ? ['jsearch', 'mock'] : ['jsearch']),
        enabled_sources: settingsMap.enabled_sources || ['linkedin', 'indeed', 'glassdoor', 'simplyhired'],
        target_states: settingsMap.target_states || ['CA', 'TX', 'FL', 'NY', 'IL', 'PA', 'OH', 'GA', 'NC', 'MI'],
        available_job_titles: mergedAvailable,
        target_job_titles: settingsMap.target_job_titles || DEFAULT_JOB_TITLES.slice(0, 16),
        target_industries: settingsMap.target_industries || TARGET_INDUSTRIES,
        company_size_priority_1_max: settingsMap.company_size_priority_1_max || 50,
        company_size_priority_2_min: settingsMap.company_size_priority_2_min || 51,
        company_size_priority_2_max: settingsMap.company_size_priority_2_max || 500,
        exclude_it_keywords: settingsMap.exclude_it_keywords || DEFAULT_IT_EXCLUSIONS,
        exclude_staffing_keywords: settingsMap.exclude_staffing_keywords || DEFAULT_STAFFING_EXCLUSIONS,
      }))

      setAIConfig(prev => ({
        ...prev,
        ai_provider: settingsMap.ai_provider || 'groq',
        groq_api_key: settingsMap.groq_api_key || '',
        openai_api_key: settingsMap.openai_api_key || '',
        anthropic_api_key: settingsMap.anthropic_api_key || '',
        gemini_api_key: settingsMap.gemini_api_key || '',
        ai_model: settingsMap.ai_model || 'llama-3.1-70b-versatile',
      }))

      setContactConfig(prev => ({
        ...prev,
        contact_provider: settingsMap.contact_provider || 'mock',
        contact_providers: settingsMap.contact_providers || (isLocal ? ['mock'] : []),
        apollo_api_key: settingsMap.apollo_api_key || '',
        seamless_api_key: settingsMap.seamless_api_key || '',
      }))

      setValidationConfig(prev => ({
        ...prev,
        email_validation_provider: settingsMap.email_validation_provider || 'mock',
        neverbounce_api_key: settingsMap.neverbounce_api_key || '',
        zerobounce_api_key: settingsMap.zerobounce_api_key || '',
        hunter_api_key: settingsMap.hunter_api_key || '',
        clearout_api_key: settingsMap.clearout_api_key || '',
        emailable_api_key: settingsMap.emailable_api_key || '',
        mailboxvalidator_api_key: settingsMap.mailboxvalidator_api_key || '',
        reacher_api_key: settingsMap.reacher_api_key || '',
        reacher_base_url: settingsMap.reacher_base_url || 'https://api.reacher.email',
      }))

      setOutreachConfig(prev => ({
        ...prev,
        email_send_mode: settingsMap.email_send_mode || 'mailmerge',
        smtp_host: settingsMap.smtp_host || '',
        smtp_port: settingsMap.smtp_port || '587',
        smtp_user: settingsMap.smtp_user || '',
        smtp_password: settingsMap.smtp_password || '',
        smtp_from_email: settingsMap.smtp_from_email || '',
        smtp_from_name: settingsMap.smtp_from_name || '',
        m365_admin_email: settingsMap.m365_admin_email || '',
        m365_admin_password: settingsMap.m365_admin_password || '',
      }))

      setBusinessRules(prev => ({
        ...prev,
        daily_send_limit: settingsMap.daily_send_limit || 30,
        cooldown_days: settingsMap.cooldown_days || 10,
        max_contacts_per_company_job: settingsMap.max_contacts_per_company_job || 4,
        min_salary_threshold: settingsMap.min_salary_threshold || 40000,
        catch_all_policy: settingsMap.catch_all_policy || 'exclude',
        unsubscribe_footer: settingsMap.unsubscribe_footer !== false,
        category_window_days: settingsMap.category_window_days ?? 90,
        category_regular_threshold: settingsMap.category_regular_threshold ?? 3,
        category_occasional_threshold: settingsMap.category_occasional_threshold ?? 0,
      }))
    } catch (err: any) {
      if (err.code !== 'ERR_CANCELED') {
        setError(err.response?.data?.detail || 'Failed to fetch settings')
      }
    } finally {
      setLoading(false)
    }
  }

  const saveSetting = async (key: string, value: any, type: string = 'string') => {
    await settingsApi.update(key, {
      value_json: JSON.stringify(value),
      type: type,
    })
  }

  const saveAllSettings = async (configType: string) => {
    try {
      setSaving(true)
      setError('')
      setSuccess('')

      if (configType === 'jobsources') {
        await Promise.all([
          saveSetting('job_source_provider', jobSourceConfig.job_source_provider),
          saveSetting('jsearch_api_key', jobSourceConfig.jsearch_api_key),
          saveSetting('indeed_publisher_id', jobSourceConfig.indeed_publisher_id),
          saveSetting('apollo_api_key', jobSourceConfig.apollo_api_key),
          saveSetting('lead_sources', jobSourceConfig.lead_sources, 'list'),
          saveSetting('enabled_sources', jobSourceConfig.enabled_sources, 'list'),
          saveSetting('target_states', jobSourceConfig.target_states, 'list'),
          saveSetting('available_job_titles', jobSourceConfig.available_job_titles, 'list'),
          saveSetting('target_job_titles', jobSourceConfig.target_job_titles, 'list'),
          saveSetting('target_industries', jobSourceConfig.target_industries, 'list'),
          saveSetting('company_size_priority_1_max', jobSourceConfig.company_size_priority_1_max, 'integer'),
          saveSetting('company_size_priority_2_min', jobSourceConfig.company_size_priority_2_min, 'integer'),
          saveSetting('company_size_priority_2_max', jobSourceConfig.company_size_priority_2_max, 'integer'),
          saveSetting('exclude_it_keywords', jobSourceConfig.exclude_it_keywords, 'list'),
          saveSetting('exclude_staffing_keywords', jobSourceConfig.exclude_staffing_keywords, 'list'),
        ])
      } else if (configType === 'ai') {
        await Promise.all([
          saveSetting('ai_provider', aiConfig.ai_provider),
          saveSetting('groq_api_key', aiConfig.groq_api_key),
          saveSetting('openai_api_key', aiConfig.openai_api_key),
          saveSetting('anthropic_api_key', aiConfig.anthropic_api_key),
          saveSetting('gemini_api_key', aiConfig.gemini_api_key),
          saveSetting('ai_model', aiConfig.ai_model),
        ])
      } else if (configType === 'contacts') {
        await Promise.all([
          saveSetting('contact_provider', contactConfig.contact_providers[0] || 'mock'),
          saveSetting('contact_providers', contactConfig.contact_providers, 'list'),
          saveSetting('apollo_api_key', contactConfig.apollo_api_key),
          saveSetting('seamless_api_key', contactConfig.seamless_api_key),
        ])
      } else if (configType === 'validation') {
        await Promise.all([
          saveSetting('email_validation_provider', validationConfig.email_validation_provider),
          saveSetting('neverbounce_api_key', validationConfig.neverbounce_api_key),
          saveSetting('zerobounce_api_key', validationConfig.zerobounce_api_key),
          saveSetting('hunter_api_key', validationConfig.hunter_api_key),
          saveSetting('clearout_api_key', validationConfig.clearout_api_key),
          saveSetting('emailable_api_key', validationConfig.emailable_api_key),
          saveSetting('mailboxvalidator_api_key', validationConfig.mailboxvalidator_api_key),
          saveSetting('reacher_api_key', validationConfig.reacher_api_key),
          saveSetting('reacher_base_url', validationConfig.reacher_base_url),
        ])
      } else if (configType === 'outreach') {
        await Promise.all([
          saveSetting('email_send_mode', outreachConfig.email_send_mode),
          saveSetting('smtp_host', outreachConfig.smtp_host),
          saveSetting('smtp_port', outreachConfig.smtp_port),
          saveSetting('smtp_user', outreachConfig.smtp_user),
          saveSetting('smtp_password', outreachConfig.smtp_password),
          saveSetting('smtp_from_email', outreachConfig.smtp_from_email),
          saveSetting('smtp_from_name', outreachConfig.smtp_from_name),
          saveSetting('m365_admin_email', outreachConfig.m365_admin_email),
          saveSetting('m365_admin_password', outreachConfig.m365_admin_password),
        ])
      } else if (configType === 'business') {
        await Promise.all([
          saveSetting('daily_send_limit', businessRules.daily_send_limit, 'integer'),
          saveSetting('cooldown_days', businessRules.cooldown_days, 'integer'),
          saveSetting('max_contacts_per_company_job', businessRules.max_contacts_per_company_job, 'integer'),
          saveSetting('min_salary_threshold', businessRules.min_salary_threshold, 'integer'),
          saveSetting('catch_all_policy', businessRules.catch_all_policy),
          saveSetting('unsubscribe_footer', businessRules.unsubscribe_footer, 'boolean'),
          saveSetting('category_window_days', businessRules.category_window_days, 'integer'),
          saveSetting('category_regular_threshold', businessRules.category_regular_threshold, 'integer'),
          saveSetting('category_occasional_threshold', businessRules.category_occasional_threshold, 'integer'),
        ])
      }

      setSuccess('Settings saved successfully!')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const testConnection = async (provider: string) => {
    try {
      setTesting(provider)
      setTestResults(prev => ({ ...prev, [provider]: { success: false, message: 'Testing...' } }))

      const response = await settingsApi.testConnection(provider)
      setTestResults(prev => ({
        ...prev,
        [provider]: {
          success: response.status === 'success',
          message: response.message || (response.status === 'success' ? 'Connection successful!' : 'Connection failed')
        }
      }))
    } catch (err: any) {
      setTestResults(prev => ({
        ...prev,
        [provider]: { success: false, message: err.response?.data?.detail || err.response?.data?.message || 'Connection failed' }
      }))
    } finally {
      setTesting(null)
    }
  }

  const getAIModels = (provider: string) => {
    switch (provider) {
      case 'groq':
        return [
          { value: 'llama-3.1-70b-versatile', label: 'Llama 3.1 70B (Recommended)' },
          { value: 'llama-3.1-8b-instant', label: 'Llama 3.1 8B (Faster)' },
          { value: 'mixtral-8x7b-32768', label: 'Mixtral 8x7B' },
          { value: 'gemma2-9b-it', label: 'Gemma 2 9B' },
        ]
      case 'openai':
        return [
          { value: 'gpt-4o', label: 'GPT-4o (Recommended)' },
          { value: 'gpt-4o-mini', label: 'GPT-4o Mini (Faster)' },
          { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
          { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
        ]
      case 'anthropic':
        return [
          { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet (Recommended)' },
          { value: 'claude-3-opus-20240229', label: 'Claude 3 Opus' },
          { value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku (Faster)' },
        ]
      case 'gemini':
        return [
          { value: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro (Recommended)' },
          { value: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash (Faster)' },
          { value: 'gemini-1.0-pro', label: 'Gemini 1.0 Pro' },
        ]
      default:
        return []
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading settings...</div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Settings</h1>
          <p className="text-gray-500 mt-1">Configure all providers, API keys, and business rules</p>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg mb-4">{error}</div>
      )}
      {success && (
        <div className="bg-green-50 text-green-600 px-4 py-2 rounded-lg mb-4">{success}</div>
      )}

      {/* Tab Navigation */}
      <div className="border-b border-gray-200 mb-6 overflow-x-auto">
        <nav className="flex space-x-4">
          {[
            { id: 'jobsources', label: '1. Job Sources', color: 'indigo' },
            { id: 'ai', label: '2. AI/LLM', color: 'pink' },
            { id: 'contacts', label: '3. Contacts', color: 'purple' },
            { id: 'validation', label: '4. Validation', color: 'cyan' },
            { id: 'outreach', label: '5. Outreach', color: 'orange' },
            { id: 'business', label: '6. Business Rules', color: 'gray' },
            { id: 'all', label: 'All Settings', color: 'gray' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`py-3 px-3 border-b-2 font-medium text-sm whitespace-nowrap ${
                activeTab === tab.id
                  ? `border-${tab.color}-500 text-${tab.color}-600`
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab 1: Job Sources */}
      {activeTab === 'jobsources' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-indigo-500 rounded-full mr-2"></span>
              Job Sources Configuration
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Configure where to fetch job postings from (LinkedIn, Indeed, Glassdoor, etc.)
            </p>

            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="label">Job Source Provider</label>
                  <select
                    value={jobSourceConfig.job_source_provider}
                    onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, job_source_provider: e.target.value })}
                    className="input"
                  >
                    <option value="mock">Mock (Development - Free)</option>
                    <option value="jsearch">JSearch API (LinkedIn, Indeed, Glassdoor)</option>
                    <option value="indeed">Indeed Publisher API</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    {jobSourceConfig.job_source_provider === 'mock' && 'Uses sample data for testing'}
                    {jobSourceConfig.job_source_provider === 'jsearch' && 'Aggregates from multiple job boards via RapidAPI'}
                    {jobSourceConfig.job_source_provider === 'indeed' && 'Direct Indeed API (requires Publisher account)'}
                  </p>
                </div>

                {jobSourceConfig.job_source_provider === 'jsearch' && (
                  <div>
                    <label className="label">JSearch API Key (RapidAPI)</label>
                    <div className="flex gap-2">
                      <input
                        type="password"
                        value={jobSourceConfig.jsearch_api_key}
                        onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, jsearch_api_key: e.target.value })}
                        placeholder="Enter RapidAPI key"
                        className="input flex-1"
                      />
                      <button
                        onClick={() => testConnection('jsearch')}
                        disabled={testing === 'jsearch' || !jobSourceConfig.jsearch_api_key}
                        className="btn-secondary text-sm"
                      >
                        {testing === 'jsearch' ? 'Testing...' : 'Test'}
                      </button>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      Get key at <a href="https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch" target="_blank" className="text-blue-600 underline">rapidapi.com/jsearch</a> (500 free requests/month)
                    </p>
                    {testResults.jsearch && (
                      <p className={`text-sm mt-1 ${testResults.jsearch.success ? 'text-green-600' : 'text-red-600'}`}>
                        {testResults.jsearch.message}
                      </p>
                    )}
                  </div>
                )}

                {jobSourceConfig.job_source_provider === 'indeed' && (
                  <div>
                    <label className="label">Indeed Publisher ID</label>
                    <div className="flex gap-2">
                      <input
                        type="password"
                        value={jobSourceConfig.indeed_publisher_id}
                        onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, indeed_publisher_id: e.target.value })}
                        placeholder="Enter Publisher ID"
                        className="input flex-1"
                      />
                      <button
                        onClick={() => testConnection('indeed')}
                        disabled={testing === 'indeed' || !jobSourceConfig.indeed_publisher_id}
                        className="btn-secondary text-sm"
                      >
                        {testing === 'indeed' ? 'Testing...' : 'Test'}
                      </button>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      Apply at <a href="https://www.indeed.com/publisher" target="_blank" className="text-blue-600 underline">indeed.com/publisher</a>
                    </p>
                  </div>
                )}
              </div>

              {/* Multi-Source Lead Configuration */}
              <div className="border-t pt-6 mt-6">
                <h4 className="font-medium text-gray-700 mb-3 flex items-center">
                  <span className="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                  Multi-Source Lead Fetching (Maximize Leads)
                </h4>
                <p className="text-sm text-gray-500 mb-4">
                  Enable multiple lead sources to maximize coverage. Duplicates are automatically removed based on company name normalization.
                </p>

                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="label">Enabled Lead Sources</label>
                    <div className="space-y-2 border rounded-lg p-3 bg-gray-50">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={jobSourceConfig.lead_sources.includes('jsearch')}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'jsearch'] })
                            } else {
                              setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter(s => s !== 'jsearch') })
                            }
                          }}
                          className="w-4 h-4"
                        />
                        <span className="text-sm font-medium">JSearch (LinkedIn, Indeed, Glassdoor)</span>
                        {jobSourceConfig.jsearch_api_key && <span className="text-xs text-green-600">API key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={jobSourceConfig.lead_sources.includes('apollo')}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'apollo'] })
                            } else {
                              setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter(s => s !== 'apollo') })
                            }
                          }}
                          className="w-4 h-4"
                        />
                        <span className="text-sm font-medium">Apollo.io (Company/People Search)</span>
                        {jobSourceConfig.apollo_api_key && <span className="text-xs text-green-600">API key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={jobSourceConfig.lead_sources.includes('mock')}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'mock'] })
                            } else {
                              setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter(s => s !== 'mock') })
                            }
                          }}
                          className="w-4 h-4"
                        />
                        <span className="text-sm font-medium">Mock (Test Data)</span>
                        {isLocalhost && <span className="text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">Auto-enabled on localhost</span>}
                      </label>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      {jobSourceConfig.lead_sources.length === 0 && <span className="text-red-500">Select at least one source</span>}
                      {jobSourceConfig.lead_sources.length === 1 && `Using ${jobSourceConfig.lead_sources[0]} only`}
                      {jobSourceConfig.lead_sources.length > 1 && `Using ${jobSourceConfig.lead_sources.length} sources with automatic deduplication`}
                    </p>
                  </div>

                  {/* Apollo API Key for Lead Sourcing */}
                  {jobSourceConfig.lead_sources.includes('apollo') && (
                    <div>
                      <label className="label">Apollo API Key (for Lead Sourcing)</label>
                      <div className="flex gap-2">
                        <input
                          type="password"
                          value={jobSourceConfig.apollo_api_key}
                          onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, apollo_api_key: e.target.value })}
                          placeholder="Enter Apollo API key"
                          className="input flex-1"
                        />
                        <button
                          onClick={() => testConnection('apollo')}
                          disabled={testing === 'apollo' || !jobSourceConfig.apollo_api_key}
                          className="btn-secondary text-sm"
                        >
                          {testing === 'apollo' ? 'Testing...' : 'Test'}
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        Get key at <a href="https://app.apollo.io/#/settings/integrations/api" target="_blank" className="text-blue-600 underline">apollo.io/settings</a>
                      </p>
                      {testResults.apollo && (
                        <p className={`text-sm mt-1 ${testResults.apollo.success ? 'text-green-600' : 'text-red-600'}`}>
                          {testResults.apollo.message}
                        </p>
                      )}
                    </div>
                  )}
                </div>

                {/* Multi-source info box */}
                <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="text-sm text-blue-700">
                    <strong>How it works:</strong> When multiple sources are enabled, leads are fetched in parallel from all sources.
                    Company names are normalized (removing Inc., Corp., LLC, etc.) and duplicates are merged, keeping the record with the most complete data.
                  </p>
                </div>
              </div>

              {/* Target States */}
              <div>
                <label className="label">Target States</label>
                <div className="border rounded-lg bg-gray-50">
                  {/* Select All checkbox */}
                  <div className="px-3 py-2 border-b bg-gray-100 rounded-t-lg">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={jobSourceConfig.target_states.length === US_STATES.length}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setJobSourceConfig({ ...jobSourceConfig, target_states: [...US_STATES] })
                          } else {
                            setJobSourceConfig({ ...jobSourceConfig, target_states: [] })
                          }
                        }}
                        className="w-4 h-4"
                      />
                      <span className="text-sm font-medium">
                        Select All ({jobSourceConfig.target_states.length}/{US_STATES.length} selected)
                      </span>
                    </label>
                  </div>
                  {/* Individual state checkboxes */}
                  <div className="flex flex-wrap gap-2 p-3">
                    {US_STATES.map((state) => (
                      <label key={state} className="flex items-center gap-1 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={jobSourceConfig.target_states.includes(state)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setJobSourceConfig({ ...jobSourceConfig, target_states: [...jobSourceConfig.target_states, state] })
                            } else {
                              setJobSourceConfig({ ...jobSourceConfig, target_states: jobSourceConfig.target_states.filter(s => s !== state) })
                            }
                          }}
                          className="w-3 h-3"
                        />
                        <span className="text-xs">{state}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-gray-500 mt-1">Select US states to search for jobs</p>
              </div>

              {/* Target Job Titles - Enhanced UI */}
              <div>
                <label className="label">Target Job Titles for Search</label>
                <p className="text-sm text-gray-500 mb-3">
                  Select which job titles to include in lead searches. You can add custom titles below.
                </p>
                <div className="border rounded-lg bg-gray-50">
                  {/* Header with Select All and count */}
                  <div className="px-3 py-2 border-b bg-gray-100 rounded-t-lg flex items-center justify-between">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={jobSourceConfig.target_job_titles.length === jobSourceConfig.available_job_titles.length}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setJobSourceConfig({ ...jobSourceConfig, target_job_titles: [...jobSourceConfig.available_job_titles] })
                          } else {
                            setJobSourceConfig({ ...jobSourceConfig, target_job_titles: [] })
                          }
                        }}
                        className="w-4 h-4"
                      />
                      <span className="text-sm font-medium">
                        Select All ({jobSourceConfig.target_job_titles.length}/{jobSourceConfig.available_job_titles.length} selected)
                      </span>
                    </label>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setJobSourceConfig({ ...jobSourceConfig, target_job_titles: jobSourceConfig.available_job_titles.slice(0, 16) })}
                        className="text-xs text-blue-600 hover:underline"
                      >
                        Select First 16
                      </button>
                      <button
                        onClick={() => setJobSourceConfig({ ...jobSourceConfig, target_job_titles: [] })}
                        className="text-xs text-gray-600 hover:underline"
                      >
                        Clear All
                      </button>
                    </div>
                  </div>
                  {/* Job titles checkboxes */}
                  <div className="flex flex-wrap gap-2 p-3 max-h-64 overflow-y-auto">
                    {jobSourceConfig.available_job_titles.map((title) => (
                      <label
                        key={title}
                        className={`flex items-center gap-1.5 cursor-pointer px-2 py-1 rounded border transition-colors ${
                          jobSourceConfig.target_job_titles.includes(title)
                            ? 'bg-blue-50 border-blue-300 text-blue-700'
                            : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={jobSourceConfig.target_job_titles.includes(title)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setJobSourceConfig({ ...jobSourceConfig, target_job_titles: [...jobSourceConfig.target_job_titles, title] })
                            } else {
                              setJobSourceConfig({ ...jobSourceConfig, target_job_titles: jobSourceConfig.target_job_titles.filter(t => t !== title) })
                            }
                          }}
                          className="w-3 h-3"
                        />
                        <span className="text-sm">{title}</span>
                        {/* Delete custom title button */}
                        {!DEFAULT_JOB_TITLES.includes(title) && (
                          <button
                            onClick={(e) => {
                              e.preventDefault()
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                available_job_titles: jobSourceConfig.available_job_titles.filter(t => t !== title),
                                target_job_titles: jobSourceConfig.target_job_titles.filter(t => t !== title)
                              })
                            }}
                            className="ml-1 text-red-400 hover:text-red-600"
                            title="Remove custom title"
                          >
                            x
                          </button>
                        )}
                      </label>
                    ))}
                  </div>
                  {/* Add new job title */}
                  <div className="px-3 py-2 border-t bg-gray-100 rounded-b-lg">
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={newJobTitle}
                        onChange={(e) => setNewJobTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && newJobTitle.trim()) {
                            e.preventDefault()
                            if (!jobSourceConfig.available_job_titles.includes(newJobTitle.trim())) {
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                available_job_titles: [...jobSourceConfig.available_job_titles, newJobTitle.trim()],
                                target_job_titles: [...jobSourceConfig.target_job_titles, newJobTitle.trim()]
                              })
                              setNewJobTitle('')
                            }
                          }
                        }}
                        placeholder="Add custom job title..."
                        className="input flex-1 text-sm"
                      />
                      <button
                        onClick={() => {
                          if (newJobTitle.trim() && !jobSourceConfig.available_job_titles.includes(newJobTitle.trim())) {
                            setJobSourceConfig({
                              ...jobSourceConfig,
                              available_job_titles: [...jobSourceConfig.available_job_titles, newJobTitle.trim()],
                              target_job_titles: [...jobSourceConfig.target_job_titles, newJobTitle.trim()]
                            })
                            setNewJobTitle('')
                          }
                        }}
                        disabled={!newJobTitle.trim() || jobSourceConfig.available_job_titles.includes(newJobTitle.trim())}
                        className="btn-secondary text-sm"
                      >
                        Add Title
                      </button>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      Press Enter or click "Add Title" to add a custom job title
                    </p>
                  </div>
                </div>
                {jobSourceConfig.target_job_titles.length === 0 && (
                  <p className="text-xs text-red-500 mt-1">Please select at least one job title for lead searches</p>
                )}
              </div>

              {jobSourceConfig.job_source_provider === 'mock' && (
                <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="text-sm text-yellow-700">
                    <strong>Mock Mode:</strong> Using simulated job data. For real job postings, configure JSearch API (recommended) or Indeed Publisher API.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Target Industries Card */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-green-500 rounded-full mr-2"></span>
              Target Industries (Non-IT Only)
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Select which industries to target for lead sourcing. IT/Tech industries are excluded by design.
            </p>
            <div className="border rounded-lg bg-gray-50">
              <div className="px-3 py-2 border-b bg-gray-100 rounded-t-lg">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={jobSourceConfig.target_industries.length === TARGET_INDUSTRIES.length}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setJobSourceConfig({ ...jobSourceConfig, target_industries: [...TARGET_INDUSTRIES] })
                      } else {
                        setJobSourceConfig({ ...jobSourceConfig, target_industries: [] })
                      }
                    }}
                    className="w-4 h-4"
                  />
                  <span className="text-sm font-medium">
                    Select All ({jobSourceConfig.target_industries.length}/{TARGET_INDUSTRIES.length} selected)
                  </span>
                </label>
              </div>
              <div className="flex flex-wrap gap-2 p-3">
                {TARGET_INDUSTRIES.map((industry) => (
                  <label key={industry} className="flex items-center gap-1.5 cursor-pointer bg-white px-2 py-1 rounded border">
                    <input
                      type="checkbox"
                      checked={jobSourceConfig.target_industries.includes(industry)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setJobSourceConfig({ ...jobSourceConfig, target_industries: [...jobSourceConfig.target_industries, industry] })
                        } else {
                          setJobSourceConfig({ ...jobSourceConfig, target_industries: jobSourceConfig.target_industries.filter(i => i !== industry) })
                        }
                      }}
                      className="w-3 h-3"
                    />
                    <span className="text-sm">{industry}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          {/* Company Size Preferences Card */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-blue-500 rounded-full mr-2"></span>
              Company Size Preferences
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Configure company size priorities for targeting. Smaller companies are prioritized first.
            </p>
            <div className="grid grid-cols-3 gap-4">
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                <h4 className="font-medium text-green-700 mb-2">Priority 1 (Preferred)</h4>
                <label className="label text-sm">Max Employees</label>
                <input
                  type="number"
                  value={jobSourceConfig.company_size_priority_1_max}
                  onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, company_size_priority_1_max: parseInt(e.target.value) || 50 })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-green-600 mt-1">Companies with up to {jobSourceConfig.company_size_priority_1_max} employees</p>
              </div>
              <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <h4 className="font-medium text-yellow-700 mb-2">Priority 2 (Secondary)</h4>
                <label className="label text-sm">Min Employees</label>
                <input
                  type="number"
                  value={jobSourceConfig.company_size_priority_2_min}
                  onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, company_size_priority_2_min: parseInt(e.target.value) || 51 })}
                  className="input mb-2"
                  min="1"
                />
                <label className="label text-sm">Max Employees</label>
                <input
                  type="number"
                  value={jobSourceConfig.company_size_priority_2_max}
                  onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, company_size_priority_2_max: parseInt(e.target.value) || 500 })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-yellow-600 mt-1">{jobSourceConfig.company_size_priority_2_min} - {jobSourceConfig.company_size_priority_2_max} employees</p>
              </div>
              <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
                <h4 className="font-medium text-gray-700 mb-2">Priority 3 (Low)</h4>
                <p className="text-sm text-gray-600 mt-4">
                  Companies with more than {jobSourceConfig.company_size_priority_2_max} employees will be deprioritized but not excluded.
                </p>
              </div>
            </div>
          </div>

          {/* Exclusion Keywords Card */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-red-500 rounded-full mr-2"></span>
              Exclusion Keywords
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Jobs or companies containing <strong>checked</strong> keywords will be automatically excluded from lead sourcing.
              Uncheck a keyword to allow it. Add custom keywords or remove non-default ones.
            </p>

            {/* Impact Info */}
            <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <p className="text-xs text-amber-800">
                <strong>IMPACT:</strong> Each checked keyword filters out ANY job/company containing it.
                Fewer checked keywords = more leads. Refined from broad terms to specific
                phrases to avoid false exclusions of legitimate non-IT roles.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-6">
              {/* IT/Tech Role Keywords */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="label mb-0">
                    <span>IT/Tech Role Keywords</span>
                    <span className="text-xs text-gray-500 ml-2">
                      ({jobSourceConfig.exclude_it_keywords.length} active)
                    </span>
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        if (jobSourceConfig.exclude_it_keywords.length === 0) {
                          setJobSourceConfig({ ...jobSourceConfig, exclude_it_keywords: DEFAULT_IT_EXCLUSIONS })
                        } else {
                          setJobSourceConfig({ ...jobSourceConfig, exclude_it_keywords: [] })
                        }
                      }}
                      className="text-xs text-blue-600 hover:text-blue-800 underline"
                    >
                      {jobSourceConfig.exclude_it_keywords.length === 0 ? 'Check All' : 'Uncheck All'}
                    </button>
                    <button
                      onClick={() => setJobSourceConfig({ ...jobSourceConfig, exclude_it_keywords: [...DEFAULT_IT_EXCLUSIONS] })}
                      className="text-xs text-gray-500 hover:text-gray-700 underline"
                    >
                      Reset Defaults
                    </button>
                  </div>
                </div>
                <div className="border border-gray-200 rounded-lg p-3 max-h-48 overflow-y-auto bg-white">
                  <div className="flex flex-wrap gap-2">
                    {Array.from(new Set([...jobSourceConfig.exclude_it_keywords, ...DEFAULT_IT_EXCLUSIONS])).sort().map((keyword) => {
                      const isActive = jobSourceConfig.exclude_it_keywords.includes(keyword)
                      const isDefault = DEFAULT_IT_EXCLUSIONS.includes(keyword)
                      return (
                        <div
                          key={keyword}
                          className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs cursor-pointer transition-all ${
                            isActive
                              ? 'bg-red-100 text-red-800 border border-red-300'
                              : 'bg-gray-100 text-gray-400 border border-gray-200 line-through'
                          }`}
                          onClick={() => {
                            if (isActive) {
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                exclude_it_keywords: jobSourceConfig.exclude_it_keywords.filter(k => k !== keyword)
                              })
                            } else {
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                exclude_it_keywords: [...jobSourceConfig.exclude_it_keywords, keyword]
                              })
                            }
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={isActive}
                            onChange={() => {}}
                            className="w-3 h-3 cursor-pointer"
                          />
                          <span>{keyword}</span>
                          {!isDefault && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                setJobSourceConfig({
                                  ...jobSourceConfig,
                                  exclude_it_keywords: jobSourceConfig.exclude_it_keywords.filter(k => k !== keyword)
                                })
                              }}
                              className="ml-1 text-red-500 hover:text-red-700 font-bold"
                              title="Remove custom keyword"
                            >
                              ×
                            </button>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
                <div className="flex gap-2 mt-2">
                  <input
                    type="text"
                    value={newITKeyword}
                    onChange={(e) => setNewITKeyword(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newITKeyword.trim()) {
                        const kw = newITKeyword.trim().toLowerCase()
                        if (!jobSourceConfig.exclude_it_keywords.includes(kw)) {
                          setJobSourceConfig({
                            ...jobSourceConfig,
                            exclude_it_keywords: [...jobSourceConfig.exclude_it_keywords, kw]
                          })
                        }
                        setNewITKeyword('')
                      }
                    }}
                    placeholder="Add custom keyword..."
                    className="input text-xs flex-1"
                  />
                  <button
                    onClick={() => {
                      const kw = newITKeyword.trim().toLowerCase()
                      if (kw && !jobSourceConfig.exclude_it_keywords.includes(kw)) {
                        setJobSourceConfig({
                          ...jobSourceConfig,
                          exclude_it_keywords: [...jobSourceConfig.exclude_it_keywords, kw]
                        })
                      }
                      setNewITKeyword('')
                    }}
                    className="btn-secondary text-xs px-3"
                  >
                    Add
                  </button>
                </div>
                <p className="text-xs text-gray-400 mt-1">Checked = excluded from results. Uncheck to allow.</p>
              </div>

              {/* Staffing/Agency Keywords */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="label mb-0">
                    <span>Staffing/Agency Keywords</span>
                    <span className="text-xs text-gray-500 ml-2">
                      ({jobSourceConfig.exclude_staffing_keywords.length} active)
                    </span>
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        if (jobSourceConfig.exclude_staffing_keywords.length === 0) {
                          setJobSourceConfig({ ...jobSourceConfig, exclude_staffing_keywords: DEFAULT_STAFFING_EXCLUSIONS })
                        } else {
                          setJobSourceConfig({ ...jobSourceConfig, exclude_staffing_keywords: [] })
                        }
                      }}
                      className="text-xs text-blue-600 hover:text-blue-800 underline"
                    >
                      {jobSourceConfig.exclude_staffing_keywords.length === 0 ? 'Check All' : 'Uncheck All'}
                    </button>
                    <button
                      onClick={() => setJobSourceConfig({ ...jobSourceConfig, exclude_staffing_keywords: [...DEFAULT_STAFFING_EXCLUSIONS] })}
                      className="text-xs text-gray-500 hover:text-gray-700 underline"
                    >
                      Reset Defaults
                    </button>
                  </div>
                </div>
                <div className="border border-gray-200 rounded-lg p-3 max-h-48 overflow-y-auto bg-white">
                  <div className="flex flex-wrap gap-2">
                    {Array.from(new Set([...jobSourceConfig.exclude_staffing_keywords, ...DEFAULT_STAFFING_EXCLUSIONS])).sort().map((keyword) => {
                      const isActive = jobSourceConfig.exclude_staffing_keywords.includes(keyword)
                      const isDefault = DEFAULT_STAFFING_EXCLUSIONS.includes(keyword)
                      return (
                        <div
                          key={keyword}
                          className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs cursor-pointer transition-all ${
                            isActive
                              ? 'bg-red-100 text-red-800 border border-red-300'
                              : 'bg-gray-100 text-gray-400 border border-gray-200 line-through'
                          }`}
                          onClick={() => {
                            if (isActive) {
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                exclude_staffing_keywords: jobSourceConfig.exclude_staffing_keywords.filter(k => k !== keyword)
                              })
                            } else {
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                exclude_staffing_keywords: [...jobSourceConfig.exclude_staffing_keywords, keyword]
                              })
                            }
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={isActive}
                            onChange={() => {}}
                            className="w-3 h-3 cursor-pointer"
                          />
                          <span>{keyword}</span>
                          {!isDefault && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                setJobSourceConfig({
                                  ...jobSourceConfig,
                                  exclude_staffing_keywords: jobSourceConfig.exclude_staffing_keywords.filter(k => k !== keyword)
                                })
                              }}
                              className="ml-1 text-red-500 hover:text-red-700 font-bold"
                              title="Remove custom keyword"
                            >
                              ×
                            </button>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
                <div className="flex gap-2 mt-2">
                  <input
                    type="text"
                    value={newStaffingKeyword}
                    onChange={(e) => setNewStaffingKeyword(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newStaffingKeyword.trim()) {
                        const kw = newStaffingKeyword.trim().toLowerCase()
                        if (!jobSourceConfig.exclude_staffing_keywords.includes(kw)) {
                          setJobSourceConfig({
                            ...jobSourceConfig,
                            exclude_staffing_keywords: [...jobSourceConfig.exclude_staffing_keywords, kw]
                          })
                        }
                        setNewStaffingKeyword('')
                      }
                    }}
                    placeholder="Add custom keyword..."
                    className="input text-xs flex-1"
                  />
                  <button
                    onClick={() => {
                      const kw = newStaffingKeyword.trim().toLowerCase()
                      if (kw && !jobSourceConfig.exclude_staffing_keywords.includes(kw)) {
                        setJobSourceConfig({
                          ...jobSourceConfig,
                          exclude_staffing_keywords: [...jobSourceConfig.exclude_staffing_keywords, kw]
                        })
                      }
                      setNewStaffingKeyword('')
                    }}
                    className="btn-secondary text-xs px-3"
                  >
                    Add
                  </button>
                </div>
                <p className="text-xs text-gray-400 mt-1">Checked = excluded from results. Uncheck to allow.</p>
              </div>
            </div>
          </div>

          <div className="flex justify-end">
            <button onClick={() => saveAllSettings('jobsources')} disabled={saving} className="btn-primary">
              {saving ? 'Saving...' : 'Save All Job Source Settings'}
            </button>
          </div>
        </div>
      )}

      {/* Tab 2: AI/LLM */}
      {activeTab === 'ai' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-pink-500 rounded-full mr-2"></span>
              AI / LLM Configuration
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Configure AI provider for email content generation, lead qualification, and other AI-powered features
            </p>

            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="label">AI Provider</label>
                <select
                  value={aiConfig.ai_provider}
                  onChange={(e) => {
                    const provider = e.target.value
                    const models = getAIModels(provider)
                    setAIConfig({
                      ...aiConfig,
                      ai_provider: provider,
                      ai_model: models[0]?.value || ''
                    })
                  }}
                  className="input"
                >
                  <option value="groq">Groq (Free & Fast - Recommended)</option>
                  <option value="openai">OpenAI (GPT-4)</option>
                  <option value="anthropic">Anthropic (Claude)</option>
                  <option value="gemini">Google (Gemini)</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {aiConfig.ai_provider === 'groq' && 'Free tier with fast inference using Llama models'}
                  {aiConfig.ai_provider === 'openai' && 'Industry-leading GPT models (paid)'}
                  {aiConfig.ai_provider === 'anthropic' && 'Claude models known for safety (paid)'}
                  {aiConfig.ai_provider === 'gemini' && 'Google\'s multimodal AI (free tier available)'}
                </p>
              </div>

              <div>
                <label className="label">Model</label>
                <select
                  value={aiConfig.ai_model}
                  onChange={(e) => setAIConfig({ ...aiConfig, ai_model: e.target.value })}
                  className="input"
                >
                  {getAIModels(aiConfig.ai_provider).map((model) => (
                    <option key={model.value} value={model.value}>{model.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* API Key based on provider */}
            <div className="mt-6">
              {aiConfig.ai_provider === 'groq' && (
                <div>
                  <label className="label">Groq API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={aiConfig.groq_api_key}
                      onChange={(e) => setAIConfig({ ...aiConfig, groq_api_key: e.target.value })}
                      placeholder="gsk_..."
                      className="input flex-1"
                    />
                    <button
                      onClick={() => testConnection('groq')}
                      disabled={testing === 'groq' || !aiConfig.groq_api_key}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'groq' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Get free key at <a href="https://console.groq.com/keys" target="_blank" className="text-blue-600 underline">console.groq.com/keys</a>
                  </p>
                  {testResults.groq && (
                    <p className={`text-sm mt-1 ${testResults.groq.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.groq.message}
                    </p>
                  )}
                </div>
              )}

              {aiConfig.ai_provider === 'openai' && (
                <div>
                  <label className="label">OpenAI API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={aiConfig.openai_api_key}
                      onChange={(e) => setAIConfig({ ...aiConfig, openai_api_key: e.target.value })}
                      placeholder="sk-..."
                      className="input flex-1"
                    />
                    <button
                      onClick={() => testConnection('openai')}
                      disabled={testing === 'openai' || !aiConfig.openai_api_key}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'openai' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Get key at <a href="https://platform.openai.com/api-keys" target="_blank" className="text-blue-600 underline">platform.openai.com</a>
                  </p>
                </div>
              )}

              {aiConfig.ai_provider === 'anthropic' && (
                <div>
                  <label className="label">Anthropic API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={aiConfig.anthropic_api_key}
                      onChange={(e) => setAIConfig({ ...aiConfig, anthropic_api_key: e.target.value })}
                      placeholder="sk-ant-..."
                      className="input flex-1"
                    />
                    <button
                      onClick={() => testConnection('anthropic')}
                      disabled={testing === 'anthropic' || !aiConfig.anthropic_api_key}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'anthropic' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Get key at <a href="https://console.anthropic.com/" target="_blank" className="text-blue-600 underline">console.anthropic.com</a>
                  </p>
                </div>
              )}

              {aiConfig.ai_provider === 'gemini' && (
                <div>
                  <label className="label">Gemini API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={aiConfig.gemini_api_key}
                      onChange={(e) => setAIConfig({ ...aiConfig, gemini_api_key: e.target.value })}
                      placeholder="AIza..."
                      className="input flex-1"
                    />
                    <button
                      onClick={() => testConnection('gemini')}
                      disabled={testing === 'gemini' || !aiConfig.gemini_api_key}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'gemini' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Get key at <a href="https://aistudio.google.com/app/apikey" target="_blank" className="text-blue-600 underline">aistudio.google.com</a>
                  </p>
                </div>
              )}
            </div>

            {/* AI Use Cases */}
            <div className="mt-6 p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium text-gray-700 mb-2">AI is used for:</h4>
              <ul className="text-sm text-gray-600 space-y-1">
                <li>- Generating personalized email content</li>
                <li>- Lead qualification and scoring</li>
                <li>- Contact research and enrichment</li>
                <li>- Response analysis and sentiment detection</li>
              </ul>
            </div>
          </div>

          <div className="flex justify-end">
            <button onClick={() => saveAllSettings('ai')} disabled={saving} className="btn-primary">
              {saving ? 'Saving...' : 'Save AI Settings'}
            </button>
          </div>
        </div>
      )}

      {/* Tab 3: Contacts */}
      {activeTab === 'contacts' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-purple-500 rounded-full mr-2"></span>
              Contact Discovery Provider
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Configure how the system finds decision-maker contacts at companies
            </p>

            <div className="space-y-4">
              <div>
                <label className="label">Enabled Providers</label>
                <div className="space-y-2 border rounded-lg p-3 bg-gray-50">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={contactConfig.contact_providers.includes('mock')} onChange={(e) => { if (e.target.checked) { setContactConfig({ ...contactConfig, contact_providers: [...contactConfig.contact_providers, 'mock'] }) } else { setContactConfig({ ...contactConfig, contact_providers: contactConfig.contact_providers.filter(s => s !== 'mock') }) } }} className="w-4 h-4" />
                    <span className="text-sm font-medium">Mock (Test Data)</span>
                    {isLocalhost && <span className="text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">Auto-enabled on localhost</span>}
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={contactConfig.contact_providers.includes('apollo')} onChange={(e) => { if (e.target.checked) { setContactConfig({ ...contactConfig, contact_providers: [...contactConfig.contact_providers, 'apollo'] }) } else { setContactConfig({ ...contactConfig, contact_providers: contactConfig.contact_providers.filter(s => s !== 'apollo') }) } }} className="w-4 h-4" />
                    <span className="text-sm font-medium">Apollo.io</span>
                    {contactConfig.apollo_api_key && <span className="text-xs text-green-600">API key configured</span>}
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={contactConfig.contact_providers.includes('seamless')} onChange={(e) => { if (e.target.checked) { setContactConfig({ ...contactConfig, contact_providers: [...contactConfig.contact_providers, 'seamless'] }) } else { setContactConfig({ ...contactConfig, contact_providers: contactConfig.contact_providers.filter(s => s !== 'seamless') }) } }} className="w-4 h-4" />
                    <span className="text-sm font-medium">Seamless.ai</span>
                    {contactConfig.seamless_api_key && <span className="text-xs text-green-600">API key configured</span>}
                  </label>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {contactConfig.contact_providers.length === 0 && <span className="text-red-500">Select at least one provider</span>}
                  {contactConfig.contact_providers.length === 1 && `Using ${contactConfig.contact_providers[0]} only`}
                  {contactConfig.contact_providers.length > 1 && `Using ${contactConfig.contact_providers.length} providers - contacts merged with deduplication`}
                </p>
              </div>

              {contactConfig.contact_providers.includes('apollo') && (
                <div>
                  <label className="label">Apollo API Key</label>
                  <div className="flex gap-2">
                    <input type="password" value={contactConfig.apollo_api_key} onChange={(e) => setContactConfig({ ...contactConfig, apollo_api_key: e.target.value })} placeholder="Enter Apollo API key" className="input flex-1" />
                    <button onClick={() => testConnection('apollo')} disabled={testing === 'apollo' || !contactConfig.apollo_api_key} className="btn-secondary text-sm">
                      {testing === 'apollo' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  {testResults.apollo && (
                    <p className={`text-sm mt-1 ${testResults.apollo.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.apollo.message}
                    </p>
                  )}
                </div>
              )}

              {contactConfig.contact_providers.includes('seamless') && (
                <div>
                  <label className="label">Seamless API Key</label>
                  <div className="flex gap-2">
                    <input type="password" value={contactConfig.seamless_api_key} onChange={(e) => setContactConfig({ ...contactConfig, seamless_api_key: e.target.value })} placeholder="Enter Seamless API key" className="input flex-1" />
                    <button onClick={() => testConnection('seamless')} disabled={testing === 'seamless' || !contactConfig.seamless_api_key} className="btn-secondary text-sm">
                      {testing === 'seamless' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {contactConfig.contact_providers.length === 1 && contactConfig.contact_providers[0] === 'mock' && (
              <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-sm text-yellow-700">
                  <strong>Mock Mode:</strong> Using simulated contact data. Add Apollo or Seamless for real contact discovery.
                </p>
              </div>
            )}
          </div>

          <div className="flex justify-end">
            <button onClick={() => saveAllSettings('contacts')} disabled={saving} className="btn-primary">
              {saving ? 'Saving...' : 'Save Contact Settings'}
            </button>
          </div>
        </div>
      )}

      {/* Tab 4: Validation */}
      {activeTab === 'validation' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-cyan-500 rounded-full mr-2"></span>
              Email Validation Provider
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Configure how the system validates email addresses before outreach
            </p>

            <div className="space-y-4">
              <div>
                <label className="label">Provider</label>
                <select
                  value={validationConfig.email_validation_provider}
                  onChange={(e) => setValidationConfig({ ...validationConfig, email_validation_provider: e.target.value })}
                  className="input"
                >
                  <option value="mock">Mock (Development)</option>
                  <optgroup label="Free Tier Providers">
                    <option value="mailboxvalidator">MailboxValidator (300 free/month)</option>
                    <option value="emailable">Emailable (250 free one-time)</option>
                    <option value="hunter">Hunter.io (25 free/month)</option>
                    <option value="reacher">Reacher (50 free/mo or self-host unlimited)</option>
                    <option value="clearout">Clearout (100 free credits)</option>
                  </optgroup>
                  <optgroup label="Paid Providers">
                    <option value="neverbounce">NeverBounce</option>
                    <option value="zerobounce">ZeroBounce</option>
                  </optgroup>
                </select>
              </div>

              {validationConfig.email_validation_provider !== 'mock' && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                  {validationConfig.email_validation_provider === 'mailboxvalidator' && 'Free: 300 verifications/month (auto-renews). Best ongoing free tier.'}
                  {validationConfig.email_validation_provider === 'emailable' && 'Free: 250 one-time credits. Good for initial validation.'}
                  {validationConfig.email_validation_provider === 'hunter' && 'Free: 25 verifications/month. Also provides email finder.'}
                  {validationConfig.email_validation_provider === 'reacher' && 'Free: 50/month cloud. Unlimited if self-hosted (open source).'}
                  {validationConfig.email_validation_provider === 'clearout' && 'Free: 100 one-time credits. Pay-as-you-go after.'}
                  {validationConfig.email_validation_provider === 'neverbounce' && 'Paid: Starts at $0.008/verification. Bulk discounts available.'}
                  {validationConfig.email_validation_provider === 'zerobounce' && 'Paid: Starts at $0.008/verification. 100 free on signup.'}
                </div>
              )}

              {validationConfig.email_validation_provider === 'neverbounce' && (
                <div>
                  <label className="label">NeverBounce API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={validationConfig.neverbounce_api_key}
                      onChange={(e) => setValidationConfig({ ...validationConfig, neverbounce_api_key: e.target.value })}
                      placeholder="Enter NeverBounce API key"
                      className="input flex-1"
                    />
                    <button
                      onClick={() => testConnection('neverbounce')}
                      disabled={testing === 'neverbounce' || !validationConfig.neverbounce_api_key}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'neverbounce' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                </div>
              )}

              {validationConfig.email_validation_provider === 'zerobounce' && (
                <div>
                  <label className="label">ZeroBounce API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={validationConfig.zerobounce_api_key}
                      onChange={(e) => setValidationConfig({ ...validationConfig, zerobounce_api_key: e.target.value })}
                      placeholder="Enter ZeroBounce API key"
                      className="input flex-1"
                    />
                    <button
                      onClick={() => testConnection('zerobounce')}
                      disabled={testing === 'zerobounce' || !validationConfig.zerobounce_api_key}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'zerobounce' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                </div>
              )}

              {validationConfig.email_validation_provider === 'hunter' && (
                <div>
                  <label className="label">Hunter.io API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={validationConfig.hunter_api_key}
                      onChange={(e) => setValidationConfig({ ...validationConfig, hunter_api_key: e.target.value })}
                      placeholder="Enter Hunter.io API key"
                      className="input flex-1"
                    />
                    <button
                      onClick={() => testConnection('hunter')}
                      disabled={testing === 'hunter' || !validationConfig.hunter_api_key}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'hunter' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                </div>
              )}

              {validationConfig.email_validation_provider === 'clearout' && (
                <div>
                  <label className="label">Clearout API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={validationConfig.clearout_api_key}
                      onChange={(e) => setValidationConfig({ ...validationConfig, clearout_api_key: e.target.value })}
                      placeholder="Enter Clearout API key"
                      className="input flex-1"
                    />
                    <button
                      onClick={() => testConnection('clearout')}
                      disabled={testing === 'clearout' || !validationConfig.clearout_api_key}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'clearout' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                </div>
              )}

              {validationConfig.email_validation_provider === 'emailable' && (
                <div>
                  <label className="label">Emailable API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={validationConfig.emailable_api_key}
                      onChange={(e) => setValidationConfig({ ...validationConfig, emailable_api_key: e.target.value })}
                      placeholder="Enter Emailable API key"
                      className="input flex-1"
                    />
                    <button
                      onClick={() => testConnection('emailable')}
                      disabled={testing === 'emailable' || !validationConfig.emailable_api_key}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'emailable' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                </div>
              )}

              {validationConfig.email_validation_provider === 'mailboxvalidator' && (
                <div>
                  <label className="label">MailboxValidator API Key</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={validationConfig.mailboxvalidator_api_key}
                      onChange={(e) => setValidationConfig({ ...validationConfig, mailboxvalidator_api_key: e.target.value })}
                      placeholder="Enter MailboxValidator API key"
                      className="input flex-1"
                    />
                    <button
                      onClick={() => testConnection('mailboxvalidator')}
                      disabled={testing === 'mailboxvalidator' || !validationConfig.mailboxvalidator_api_key}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'mailboxvalidator' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                </div>
              )}

              {validationConfig.email_validation_provider === 'reacher' && (
                <div className="space-y-3">
                  <div>
                    <label className="label">Reacher API Key</label>
                    <div className="flex gap-2">
                      <input
                        type="password"
                        value={validationConfig.reacher_api_key}
                        onChange={(e) => setValidationConfig({ ...validationConfig, reacher_api_key: e.target.value })}
                        placeholder="Enter Reacher API key (optional if self-hosted)"
                        className="input flex-1"
                      />
                      <button
                        onClick={() => testConnection('reacher')}
                        disabled={testing === 'reacher'}
                        className="btn-secondary text-sm"
                      >
                        {testing === 'reacher' ? 'Testing...' : 'Test'}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="label">Reacher Base URL</label>
                    <input
                      type="text"
                      value={validationConfig.reacher_base_url}
                      onChange={(e) => setValidationConfig({ ...validationConfig, reacher_base_url: e.target.value })}
                      placeholder="https://api.reacher.email"
                      className="input"
                    />
                    <p className="text-xs text-gray-400 mt-1">Use default for cloud, or enter your self-hosted URL</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-end">
            <button onClick={() => saveAllSettings('validation')} disabled={saving} className="btn-primary">
              {saving ? 'Saving...' : 'Save Validation Settings'}
            </button>
          </div>
        </div>
      )}

      {/* Tab 5: Outreach */}
      {activeTab === 'outreach' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-orange-500 rounded-full mr-2"></span>
              Outreach / Email Sending
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Configure how the system sends outreach emails
            </p>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="label">Send Mode</label>
                  <select
                    value={outreachConfig.email_send_mode}
                    onChange={(e) => {
                      const mode = e.target.value
                      if (mode === 'microsoft365') {
                        setOutreachConfig({
                          ...outreachConfig,
                          email_send_mode: mode,
                          smtp_host: 'smtp.office365.com',
                          smtp_port: '587'
                        })
                      } else {
                        setOutreachConfig({ ...outreachConfig, email_send_mode: mode })
                      }
                    }}
                    className="input"
                  >
                    <option value="mailmerge">Mail Merge Export (CSV)</option>
                    <option value="microsoft365">Microsoft 365 (Direct Send)</option>
                    <option value="smtp">Custom SMTP (Direct Send)</option>
                    <option value="mock">Mock (Development)</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    {outreachConfig.email_send_mode === 'mailmerge' && 'Export CSV for use with external mail merge tools'}
                    {outreachConfig.email_send_mode === 'microsoft365' && 'Send directly via Microsoft 365 / Office 365'}
                    {outreachConfig.email_send_mode === 'smtp' && 'Send via custom SMTP server'}
                    {outreachConfig.email_send_mode === 'mock' && 'Simulate sending for testing'}
                  </p>
                </div>
              </div>

              {/* Microsoft 365 Configuration */}
              {outreachConfig.email_send_mode === 'microsoft365' && (
                <div className="border-t pt-4 mt-4">
                  <h4 className="font-medium text-gray-700 mb-3 flex items-center">
                    <svg className="w-5 h-5 mr-2 text-blue-600" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M21.17 3.25q.33 0 .59.25.25.24.25.58v15.84q0 .34-.25.59-.26.25-.59.25H7.83q-.33 0-.59-.25-.25-.25-.25-.59V4.08q0-.34.25-.58.26-.25.59-.25zm-9.5 2.5v4.5h-4.5V12h4.5v4.5h4.5V12h-4.5V5.75zm1 12.75v-4.5h4.5v4.5zm4.5-5.5v-4.5h-4.5v4.5z"/>
                    </svg>
                    Microsoft 365 Configuration
                  </h4>
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                    <p className="text-sm text-blue-700">
                      <strong>Note:</strong> Microsoft 365 requires SMTP AUTH to be enabled for the account.
                      Go to Microsoft 365 Admin Center → Users → Select User → Mail → Email apps → Enable Authenticated SMTP.
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="label">M365 Admin Email</label>
                      <input
                        type="email"
                        value={outreachConfig.m365_admin_email}
                        onChange={(e) => setOutreachConfig({ ...outreachConfig, m365_admin_email: e.target.value })}
                        placeholder="admin@yourdomain.com"
                        className="input"
                      />
                      <p className="text-xs text-gray-500 mt-1">Account with SMTP AUTH enabled</p>
                    </div>
                    <div>
                      <label className="label">M365 Password</label>
                      <input
                        type="password"
                        value={outreachConfig.m365_admin_password}
                        onChange={(e) => setOutreachConfig({ ...outreachConfig, m365_admin_password: e.target.value })}
                        placeholder="Password or App Password"
                        className="input"
                      />
                      <p className="text-xs text-gray-500 mt-1">Use App Password if 2FA enabled</p>
                    </div>
                    <div>
                      <label className="label">SMTP Host</label>
                      <input
                        type="text"
                        value={outreachConfig.smtp_host}
                        onChange={(e) => setOutreachConfig({ ...outreachConfig, smtp_host: e.target.value })}
                        placeholder="smtp.office365.com"
                        className="input bg-gray-50"
                      />
                    </div>
                    <div>
                      <label className="label">SMTP Port</label>
                      <input
                        type="text"
                        value={outreachConfig.smtp_port}
                        onChange={(e) => setOutreachConfig({ ...outreachConfig, smtp_port: e.target.value })}
                        placeholder="587"
                        className="input bg-gray-50"
                      />
                    </div>
                  </div>
                  <div className="mt-4">
                    <button
                      onClick={() => testConnection('m365')}
                      disabled={testing === 'm365' || !outreachConfig.m365_admin_email}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'm365' ? 'Testing...' : 'Test M365 Connection'}
                    </button>
                    {testResults.m365 && (
                      <p className={`text-sm mt-2 ${testResults.m365.success ? 'text-green-600' : 'text-red-600'}`}>
                        {testResults.m365.message}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Custom SMTP Configuration */}
              {outreachConfig.email_send_mode === 'smtp' && (
                <div className="border-t pt-4 mt-4">
                  <h4 className="font-medium text-gray-700 mb-3">Custom SMTP Configuration</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="label">SMTP Host</label>
                      <input
                        type="text"
                        value={outreachConfig.smtp_host}
                        onChange={(e) => setOutreachConfig({ ...outreachConfig, smtp_host: e.target.value })}
                        placeholder="smtp.gmail.com"
                        className="input"
                      />
                    </div>
                    <div>
                      <label className="label">SMTP Port</label>
                      <input
                        type="text"
                        value={outreachConfig.smtp_port}
                        onChange={(e) => setOutreachConfig({ ...outreachConfig, smtp_port: e.target.value })}
                        placeholder="587"
                        className="input"
                      />
                    </div>
                    <div>
                      <label className="label">Username</label>
                      <input
                        type="text"
                        value={outreachConfig.smtp_user}
                        onChange={(e) => setOutreachConfig({ ...outreachConfig, smtp_user: e.target.value })}
                        placeholder="your@email.com"
                        className="input"
                      />
                    </div>
                    <div>
                      <label className="label">Password</label>
                      <input
                        type="password"
                        value={outreachConfig.smtp_password}
                        onChange={(e) => setOutreachConfig({ ...outreachConfig, smtp_password: e.target.value })}
                        placeholder="App password"
                        className="input"
                      />
                    </div>
                    <div>
                      <label className="label">From Email</label>
                      <input
                        type="email"
                        value={outreachConfig.smtp_from_email}
                        onChange={(e) => setOutreachConfig({ ...outreachConfig, smtp_from_email: e.target.value })}
                        placeholder="outreach@company.com"
                        className="input"
                      />
                    </div>
                    <div>
                      <label className="label">From Name</label>
                      <input
                        type="text"
                        value={outreachConfig.smtp_from_name}
                        onChange={(e) => setOutreachConfig({ ...outreachConfig, smtp_from_name: e.target.value })}
                        placeholder="Your Name"
                        className="input"
                      />
                    </div>
                  </div>
                  <div className="mt-4">
                    <button
                      onClick={() => testConnection('smtp')}
                      disabled={testing === 'smtp' || !outreachConfig.smtp_host}
                      className="btn-secondary text-sm"
                    >
                      {testing === 'smtp' ? 'Testing...' : 'Test SMTP Connection'}
                    </button>
                    {testResults.smtp && (
                      <p className={`text-sm mt-2 ${testResults.smtp.success ? 'text-green-600' : 'text-red-600'}`}>
                        {testResults.smtp.message}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Mailbox Rotation Info */}
              {(outreachConfig.email_send_mode === 'microsoft365' || outreachConfig.email_send_mode === 'smtp') && (
                <div className="mt-4 p-4 bg-gray-50 rounded-lg border">
                  <h4 className="font-medium text-gray-700 mb-2">Sender Mailboxes</h4>
                  <p className="text-sm text-gray-600 mb-2">
                    The system uses multiple sender mailboxes for email rotation. Configure them in the <a href="/dashboard/mailboxes" className="text-blue-600 underline">Mailboxes</a> page.
                  </p>
                  <p className="text-sm text-gray-500">
                    Microsoft 365 admin credentials above are used for authentication. Individual sender mailboxes must have SMTP AUTH enabled.
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-end">
            <button onClick={() => saveAllSettings('outreach')} disabled={saving} className="btn-primary">
              {saving ? 'Saving...' : 'Save Outreach Settings'}
            </button>
          </div>
        </div>
      )}

      {/* Tab 6: Business Rules */}
      {activeTab === 'business' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">Outreach Limits</h3>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="label">Daily Send Limit</label>
                <input
                  type="number"
                  value={businessRules.daily_send_limit}
                  onChange={(e) => setBusinessRules({ ...businessRules, daily_send_limit: parseInt(e.target.value) || 0 })}
                  className="input"
                />
                <p className="text-xs text-gray-500 mt-1">Max emails per day (recommended: 30-50)</p>
              </div>
              <div>
                <label className="label">Cooldown Period (Days)</label>
                <input
                  type="number"
                  value={businessRules.cooldown_days}
                  onChange={(e) => setBusinessRules({ ...businessRules, cooldown_days: parseInt(e.target.value) || 0 })}
                  className="input"
                />
              </div>
              <div>
                <label className="label">Max Contacts per Company/Job</label>
                <input
                  type="number"
                  value={businessRules.max_contacts_per_company_job}
                  onChange={(e) => setBusinessRules({ ...businessRules, max_contacts_per_company_job: parseInt(e.target.value) || 0 })}
                  className="input"
                />
              </div>
              <div>
                <label className="label">Min Salary Threshold ($)</label>
                <input
                  type="number"
                  value={businessRules.min_salary_threshold}
                  onChange={(e) => setBusinessRules({ ...businessRules, min_salary_threshold: parseInt(e.target.value) || 0 })}
                  className="input"
                  step="5000"
                />
              </div>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">Email Policies</h3>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="label">Catch-All Email Policy</label>
                <select
                  value={businessRules.catch_all_policy}
                  onChange={(e) => setBusinessRules({ ...businessRules, catch_all_policy: e.target.value })}
                  className="input"
                >
                  <option value="exclude">Exclude (Safer)</option>
                  <option value="include">Include (Risky)</option>
                  <option value="flag">Flag for Review</option>
                </select>
              </div>
              <div>
                <label className="label">Unsubscribe Footer</label>
                <div className="flex items-center gap-3 mt-2">
                  <input
                    type="checkbox"
                    checked={businessRules.unsubscribe_footer}
                    onChange={(e) => setBusinessRules({ ...businessRules, unsubscribe_footer: e.target.checked })}
                    className="w-4 h-4"
                  />
                  <span className="text-sm">Include unsubscribe link (CAN-SPAM compliance)</span>
                </div>
              </div>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2">Client Category Rules</h3>
            <p className="text-sm text-gray-500 mb-4">
              Controls how clients are auto-classified as Regular, Occasional, or Prospect based on their job posting frequency.
            </p>
            <div className="grid grid-cols-3 gap-6">
              <div>
                <label className="label">Lookback Window (Days)</label>
                <input
                  type="number"
                  value={businessRules.category_window_days}
                  onChange={(e) => setBusinessRules({ ...businessRules, category_window_days: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-gray-500 mt-1">How far back to count posting dates (default: 90)</p>
              </div>
              <div>
                <label className="label">Regular Threshold</label>
                <input
                  type="number"
                  value={businessRules.category_regular_threshold}
                  onChange={(e) => setBusinessRules({ ...businessRules, category_regular_threshold: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-gray-500 mt-1">Unique posting dates &gt; this = Regular (default: 3)</p>
              </div>
              <div>
                <label className="label">Occasional Threshold</label>
                <input
                  type="number"
                  value={businessRules.category_occasional_threshold}
                  onChange={(e) => setBusinessRules({ ...businessRules, category_occasional_threshold: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="0"
                />
                <p className="text-xs text-gray-500 mt-1">Unique posting dates &gt; this = Occasional (default: 0)</p>
              </div>
            </div>
            <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-700">
              <p className="font-medium mb-1">How it works:</p>
              <ul className="list-disc ml-4 space-y-1">
                <li><span className="font-medium text-green-700">Regular</span> — more than {businessRules.category_regular_threshold} unique posting dates in the last {businessRules.category_window_days} days</li>
                <li><span className="font-medium text-blue-700">Occasional</span> — more than {businessRules.category_occasional_threshold} but &le; {businessRules.category_regular_threshold} unique posting dates</li>
                <li><span className="font-medium text-yellow-700">Prospect</span> — {businessRules.category_occasional_threshold} or fewer unique posting dates</li>
                <li><span className="font-medium text-gray-600">Dormant</span> — manually assigned only</li>
              </ul>
            </div>
          </div>

          <div className="flex justify-end">
            <button onClick={() => saveAllSettings('business')} disabled={saving} className="btn-primary">
              {saving ? 'Saving...' : 'Save Business Rules'}
            </button>
          </div>
        </div>
      )}

      {/* Tab 7: All Settings */}
      {activeTab === 'all' && (
        <div className="card overflow-hidden">
          <div className="divide-y divide-gray-200 max-h-96 overflow-y-auto">
            {settings.map((setting) => (
              <div key={setting.key} className="py-3 px-4 flex justify-between items-center text-sm">
                <div>
                  <span className="font-mono text-gray-900">{setting.key}</span>
                  <span className="text-gray-400 ml-2">({setting.type})</span>
                </div>
                <span className="font-mono bg-gray-100 px-2 py-1 rounded text-xs max-w-xs truncate">
                  {setting.key.includes('api_key') || setting.key.includes('password')
                    ? '••••••••'
                    : (() => {
                        try {
                          const val = JSON.parse(setting.value_json)
                          if (Array.isArray(val)) return `[${val.length} items]`
                          return typeof val === 'boolean' ? (val ? 'Yes' : 'No') : String(val)
                        } catch { return setting.value_json }
                      })()}
                </span>
              </div>
            ))}
          </div>
          {settings.length === 0 && (
            <div className="text-center py-8 text-gray-500">No settings found</div>
          )}
          <div className="p-4 border-t bg-gray-50">
            <button
              onClick={async () => {
                try {
                  await settingsApi.initialize()
                  fetchSettings()
                  setSuccess('Settings initialized!')
                } catch (err: any) {
                  setError('Failed to initialize settings')
                }
              }}
              className="btn-secondary text-sm"
            >
              Initialize Default Settings
            </button>
          </div>
        </div>
      )}

      {/* Pipeline Summary */}
      <div className="mt-8 card p-6 bg-gradient-to-r from-gray-50 to-gray-100">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Complete Pipeline Configuration Summary</h3>
        <div className="grid grid-cols-5 gap-3 text-sm">
          <div className="bg-white p-3 rounded-lg border-l-4 border-indigo-500">
            <div className="font-semibold text-indigo-600">1. Job Sources</div>
            <div className="text-gray-600 mt-1">
              {jobSourceConfig.lead_sources.length > 1
                ? `${jobSourceConfig.lead_sources.length} sources`
                : jobSourceConfig.lead_sources[0] || 'None'}
            </div>
          </div>
          <div className="bg-white p-3 rounded-lg border-l-4 border-pink-500">
            <div className="font-semibold text-pink-600">2. AI/LLM</div>
            <div className="text-gray-600 mt-1">{aiConfig.ai_provider}</div>
          </div>
          <div className="bg-white p-3 rounded-lg border-l-4 border-purple-500">
            <div className="font-semibold text-purple-600">3. Contacts</div>
            <div className="text-gray-600 mt-1">{contactConfig.contact_providers.join(", ") || "none"}</div>
          </div>
          <div className="bg-white p-3 rounded-lg border-l-4 border-cyan-500">
            <div className="font-semibold text-cyan-600">4. Validation</div>
            <div className="text-gray-600 mt-1">{validationConfig.email_validation_provider}</div>
          </div>
          <div className="bg-white p-3 rounded-lg border-l-4 border-orange-500">
            <div className="font-semibold text-orange-600">5. Outreach</div>
            <div className="text-gray-600 mt-1">{outreachConfig.email_send_mode}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

