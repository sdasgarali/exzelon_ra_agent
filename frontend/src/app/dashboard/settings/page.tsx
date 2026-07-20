'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
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
  lead_sources: string[]  // Enabled lead sources: jsearch, theirstack, serpapi, adzuna (Apollo is contact-enrichment only)
  enabled_sources: string[]
  target_states: string[]
  available_job_titles: string[]  // Master list of all available titles (derived from categories)
  target_job_titles: string[]     // Currently selected/active titles for search
  job_title_categories: Record<string, string[]>  // Titles grouped by category
  target_industries: string[]
  company_size_priority_1_max: number
  company_size_priority_2_min: number
  company_size_priority_2_max: number
  company_size_no_preference: boolean
  exclude_it_keywords: string[]
  exclude_staffing_keywords: string[]
  exclude_company_keywords: string[]
  exclude_title_keywords: string[]
  exclude_match_mode: 'word_boundary' | 'substring'
  lead_sourcing_frequency: '2x' | '4x' | '6x'
  location_diversification: boolean
  theirstack_api_key: string
  serpapi_api_key: string
  adzuna_app_id: string
  adzuna_api_key: string
  searchapi_api_key: string
  usajobs_api_key: string
  usajobs_email: string
  jooble_api_key: string
  jobdatafeeds_api_key: string
  coresignal_api_key: string
  fantastic_jobs_api_key: string
}

interface AIConfig {
  ai_provider: string
  groq_api_key: string
  openai_api_key: string
  anthropic_api_key: string
  gemini_api_key: string
  ai_model: string
  ai_personalize_emails: string
  ai_personalization_prompt: string
}

interface ContactConfig {
  contact_provider: string
  contact_providers: string[]
  apollo_api_key: string
  seamless_api_key: string
  hunter_contact_api_key: string
  snovio_client_id: string
  snovio_client_secret: string
  rocketreach_api_key: string
  pdl_api_key: string
  proxycurl_api_key: string
  clearbit_api_key: string
  opencorporates_api_key: string
  company_enrichment_providers: string[]
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
  data_retention_days: number
  domain_daily_limit_default: number
  domain_daily_limit_major_providers: number
  max_contacts_per_company_all_campaigns: number
  send_delay_min_sec: number
  send_delay_max_sec: number
}

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
]

const DEFAULT_JOB_TITLE_CATEGORIES: Record<string, string[]> = {
  "HR & Talent": ["HR Manager", "HR Director", "HR Business Partner", "HR Generalist", "HR Coordinator", "Recruiter", "Talent Acquisition", "Talent Acquisition Manager", "Staffing Coordinator", "Staffing Manager", "Talent Manager", "Workforce Manager", "Recruitment Manager", "People Operations Manager", "Employee Relations Manager", "Compensation Manager", "Benefits Manager", "Payroll Manager", "VP Human Resources", "Director of HR", "Chief People Officer"],
  "Operations & General Management": ["Operations Manager", "Operations Director", "VP Operations", "Director of Operations", "COO", "Chief Operating Officer", "General Manager", "Assistant General Manager", "Regional Manager", "Area Manager", "District Manager", "Territory Manager", "Branch Manager", "Site Manager", "Field Manager"],
  "Manufacturing": ["Manufacturing Manager", "Manufacturing Director", "Manufacturing Supervisor", "Manufacturing Engineer", "Manufacturing Technician", "Lean Manager", "Continuous Improvement Manager", "Process Improvement Manager"],
  "Production": ["Plant Manager", "Production Manager", "Production Supervisor", "Production Coordinator", "Production Planner", "Production Scheduler", "Production Control Manager", "Production Lead"],
  "Warehouse & Logistics": ["Warehouse Manager", "Warehouse Supervisor", "Warehouse Director", "Distribution Manager", "Distribution Center Manager", "Logistics Manager", "Logistics Director", "Logistics Coordinator", "Supply Chain Manager", "Supply Chain Director", "Inventory Manager", "Inventory Control Manager", "Shipping Manager", "Receiving Manager", "Freight Manager", "Fleet Manager", "Dispatch Manager", "Transportation Manager"],
  "Facilities": ["Facilities Manager", "Facilities Director", "Facilities Coordinator", "Facilities Supervisor", "Building Manager", "Building Engineer", "Property Manager", "Property Management Director"],
  "Maintenance": ["Maintenance Manager", "Maintenance Director", "Maintenance Supervisor", "Maintenance Coordinator", "Maintenance Technician", "Maintenance Planner", "Maintenance Engineer"],
  "Safety & Compliance": ["Safety Manager", "Safety Director", "Safety Coordinator", "EHS Manager", "Environmental Health Safety Manager", "HSE Manager", "Compliance Manager", "Compliance Director", "Compliance Officer", "Risk Manager", "Risk Director", "Loss Prevention Manager", "Claims Manager", "Regulatory Affairs Manager"],
  "Construction": ["Construction Manager", "Construction Superintendent", "Construction Director", "Construction Foreman", "Construction Estimator", "Construction Inspector", "General Contractor", "Site Superintendent"],
  "Engineering": ["Engineering Manager", "Engineering Director", "Chief Engineer", "Mechanical Engineer", "Civil Engineer", "Structural Engineer", "Design Engineer", "Project Engineer", "Field Engineer"],
  "Quality": ["Quality Manager", "Quality Control Manager", "Quality Assurance Manager", "Quality Director", "Quality Engineer", "Quality Inspector", "Quality Supervisor", "Quality Technician"],
  "CNC": ["CNC Machinist", "CNC Operator", "CNC Programmer", "CNC Supervisor", "CNC Manager", "CNC Setup Technician", "CNC Mill Operator", "CNC Lathe Operator", "CNC Lead"],
  "Accounting": ["Accountant", "CPA", "Accounting Manager", "Accounting Director", "Accounting Supervisor", "Accounts Payable Manager", "Accounts Receivable Manager", "Staff Accountant", "Senior Accountant", "Cost Accountant", "Tax Accountant", "Accounting Clerk"],
  "Bookkeeper": ["Bookkeeper", "Full Charge Bookkeeper", "Senior Bookkeeper", "Bookkeeping Manager", "Bookkeeping Supervisor"],
  "Controller": ["Controller", "Assistant Controller", "Corporate Controller", "Division Controller", "Plant Controller", "Regional Controller"],
  "Financial": ["Finance Manager", "Finance Director", "CFO", "Chief Financial Officer", "Financial Analyst", "Financial Controller", "Financial Planner", "Credit Manager", "Collections Manager", "Treasury Manager"],
  "Tax": ["Tax Manager", "Tax Director", "Tax Analyst", "Tax Accountant", "Tax Preparer", "Tax Specialist", "Tax Supervisor"],
  "Insurance": ["Insurance Manager", "Insurance Agent", "Insurance Underwriter", "Insurance Adjuster", "Claims Manager", "Claims Adjuster", "Insurance Director", "Risk Manager"],
  "Architecture": ["Architect", "Senior Architect", "Architecture Manager", "Architectural Designer", "Project Architect", "Design Manager", "Interior Architect", "Landscape Architect"],
  "Interior Designer": ["Interior Designer", "Senior Interior Designer", "Interior Design Manager", "Interior Design Director", "Space Planner", "Design Coordinator"],
  "Purchasing & Procurement": ["Purchasing Manager", "Purchasing Director", "Purchasing Agent", "Procurement Manager", "Procurement Director", "Procurement Specialist", "Buyer", "Senior Buyer", "Category Manager", "Vendor Manager", "Supplier Manager"],
  "Hospitality & Food Service": ["Restaurant Manager", "Restaurant General Manager", "Hotel Manager", "Hotel General Manager", "Front Desk Manager", "Food Service Manager", "Food Service Director", "Banquet Manager", "Catering Manager", "Housekeeping Manager", "Housekeeping Director", "Executive Chef", "Kitchen Manager"],
  "Food Industry": ["Food Production Manager", "Food Safety Manager", "Food Plant Manager", "Food Quality Manager", "Food Processing Supervisor", "Bakery Manager", "Dairy Manager", "Meat Processing Manager"],
  "Retail": ["Store Manager", "Store Director", "Retail Manager", "Assistant Store Manager", "Retail Operations Manager", "Merchandise Manager", "Visual Merchandising Manager", "Retail District Manager", "Retail Regional Manager"],
  "Sales": ["Account Manager", "Sales Manager", "Regional Sales Manager", "Business Development Manager", "Service Manager", "Customer Service Manager", "Call Center Manager", "Sales Director", "VP Sales", "Inside Sales Manager", "Outside Sales Manager", "Territory Sales Manager"],
  "Healthcare & Social Services": ["Nurse Manager", "Nursing Director", "Director of Nursing", "Clinical Manager", "Practice Manager", "Office Manager", "Healthcare Administrator", "Hospital Administrator", "Social Services Director", "Case Manager"],
  "Education": ["School Principal", "Assistant Principal", "Academic Director", "Education Director", "Training Manager", "Training Director", "Learning and Development Manager", "Organizational Development Manager", "Curriculum Director", "Dean"],
  "HVAC": ["HVAC Manager", "HVAC Supervisor", "HVAC Technician", "HVAC Installer", "HVAC Service Manager", "HVAC Director", "Refrigeration Manager", "Refrigeration Technician"],
  "Electrical": ["Electrical Manager", "Electrical Supervisor", "Electrical Engineer", "Electrical Foreman", "Master Electrician", "Electrical Director", "Electrical Contractor", "Electrical Superintendent"],
  "Technicians": ["Service Technician", "Field Service Technician", "Maintenance Technician", "Industrial Technician", "Equipment Technician", "Lab Technician", "Technical Manager", "Technical Director"],
  "Field Service": ["Field Service Manager", "Field Service Director", "Field Service Engineer", "Field Service Supervisor", "Field Service Coordinator", "Field Operations Manager", "Service Dispatch Manager"],
  "Mining": ["Mine Manager", "Mine Superintendent", "Mine Engineer", "Mining Supervisor", "Mining Director", "Quarry Manager", "Drilling Manager", "Geology Manager"],
  "Solar": ["Solar Project Manager", "Solar Installation Manager", "Solar Director", "Solar Operations Manager", "Solar Site Supervisor", "Renewable Energy Manager", "Energy Manager"],
  "Industrial": ["Industrial Manager", "Industrial Engineer", "Industrial Supervisor", "Industrial Maintenance Manager", "Industrial Production Manager", "Plant Engineer", "Plant Superintendent"],
  "Injection Molding": ["Injection Molding Manager", "Injection Molding Supervisor", "Molding Manager", "Molding Technician", "Plastics Manager", "Plastics Engineer", "Extrusion Manager"],
  "Process Engineer": ["Process Engineer", "Senior Process Engineer", "Process Engineering Manager", "Process Improvement Engineer", "Process Development Engineer", "Chemical Engineer", "Process Technician"],
  "Plant Management": ["Plant Manager", "Plant Director", "Plant Superintendent", "Plant Engineer", "Plant Supervisor", "Plant Operations Manager", "Assistant Plant Manager"],
  "Supervisor": ["Production Supervisor", "Warehouse Supervisor", "Shift Supervisor", "Team Leader", "Team Supervisor", "Lead Supervisor", "Night Shift Supervisor", "Day Shift Supervisor", "Area Supervisor", "Line Supervisor"],
  "Manager": ["Project Manager", "Senior Project Manager", "Program Manager", "Department Manager", "Division Manager", "Office Manager", "Administrative Manager", "Business Manager"],
  "Attorney": ["Attorney", "General Counsel", "Corporate Counsel", "Legal Director", "Legal Manager", "Paralegal Manager", "Compliance Attorney", "Employment Attorney"],
  "Entry Level": ["Administrative Assistant", "Office Coordinator", "Receptionist", "Data Entry Clerk", "File Clerk", "Mail Room Clerk", "Customer Service Representative", "Order Entry Clerk"],
  "Staff Account": ["Staff Accountant", "Junior Accountant", "Accounting Associate", "Accounting Specialist", "Accounting Coordinator", "AP Clerk", "AR Clerk", "Billing Clerk"],
  "Agriculture & Trades": ["Farm Manager", "Ranch Manager", "Ag Operations Manager", "Shop Manager", "Foreman", "Superintendent", "Trades Manager", "Skilled Trades Supervisor"],
}

// Derive flat list from categories
const DEFAULT_JOB_TITLES = Array.from(new Set(Object.values(DEFAULT_JOB_TITLE_CATEGORIES).flat())).sort()

const TARGET_INDUSTRIES = [
  'Healthcare', 'Manufacturing', 'Logistics', 'Retail', 'BFSI',
  'Education', 'Engineering', 'Automotive', 'Construction', 'Energy',
  'Oil & Gas', 'Food & Beverage', 'Hospitality', 'Real Estate',
  'Legal', 'Financial Services', 'Industrial',
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
  'employment agency', 'executive search firm',
  'recruitment', 'government', 'administration',
  'medical', 'non profit', 'nonprofit',
  'civics', 'social services',
  'computer security', 'network security', 'security agency',
  'telecommunication',
  'primary education', 'secondary education', 'university',
  'religious', 'church',
]

const DEFAULT_COMPANY_EXCLUSIONS = [
  'staffing agency', 'staffing firm', 'recruitment agency',
  'talent acquisition agency', 'temp agency',
  'employment agency', 'executive search firm',
  'security agency',
]

const DEFAULT_TITLE_EXCLUSIONS = [
  'intern', 'entry level',
]

const DEFAULT_AI_PERSONALIZATION_PROMPT = `You are an expert cold email personalizer for a staffing/recruitment agency.

Rewrite the given email to be uniquely personalized for this specific contact.

RULES:
1. Use the contact's profile naturally (name, title, company, industry, location, job context)
2. Maintain the core message, value proposition, and CTA from the original
3. Keep under 120 words — shorter is more human
4. Write as a busy sales pro typing between meetings
5. Vary sentence length — mix short (3-5 words) with longer ones
6. Include one natural imperfection (dash, ellipsis, parenthetical)
7. NEVER use: "I hope this finds you well", "reaching out", "cutting-edge", "synergy"
8. Use first-person observations: "I noticed", "I saw that"
9. Reference something specific about THEIR situation
10. Short paragraphs (1-2 sentences)

ANTI-AI-DETECTION:
- Write like a slightly rushed but professional human
- Mix contractions inconsistently
- Avoid uniform sentence length
- One imperfection makes it authentic

OUTPUT FORMAT (strict):
SUBJECT: [rewritten subject, under 50 chars]
---
[email body as HTML with <p> tags only]
---
[email body as plain text]`

// Tab ID to permission key mapping
const TAB_PERM_MAP: Record<string, string> = {
  jobfilters: 'job_filters',
  jobsourceapis: 'job_source_apis',
  ai: 'ai_llm',
  contacts: 'contacts',
  validation: 'validation',
  outreach: 'outreach',
  business: 'business_rules',
  deliverability: 'deliverability',
  lobleadsources: 'lob_lead_sources',
  sourcetuning: 'source_tuning',
}

// Setting key to tab mapping (for All Settings filtering)
const SETTING_TAB_MAP: Record<string, string> = {
  target_states: 'job_filters', available_job_titles: 'job_filters', target_job_titles: 'job_filters',
  target_industries: 'job_filters', company_size_priority_1_max: 'job_filters',
  company_size_priority_2_min: 'job_filters', company_size_priority_2_max: 'job_filters',
  company_size_no_preference: 'job_filters',
  exclude_it_keywords: 'job_filters', exclude_staffing_keywords: 'job_filters', job_title_categories: 'job_filters',
  job_source_provider: 'job_source_apis', jsearch_api_key: 'job_source_apis', indeed_publisher_id: 'job_source_apis',
  apollo_api_key: 'contacts', lead_sources: 'job_source_apis', enabled_sources: 'job_source_apis',
  theirstack_api_key: 'job_source_apis', serpapi_api_key: 'job_source_apis',
  adzuna_app_id: 'job_source_apis', adzuna_api_key: 'job_source_apis',
  searchapi_api_key: 'job_source_apis', usajobs_api_key: 'job_source_apis', usajobs_email: 'job_source_apis',
  jooble_api_key: 'job_source_apis', jobdatafeeds_api_key: 'job_source_apis', coresignal_api_key: 'job_source_apis',
  ai_provider: 'ai_llm', groq_api_key: 'ai_llm', openai_api_key: 'ai_llm',
  anthropic_api_key: 'ai_llm', gemini_api_key: 'ai_llm', ai_model: 'ai_llm',
  ai_personalize_emails: 'ai_llm', ai_personalization_prompt: 'ai_llm',
  contact_provider: 'contacts', contact_providers: 'contacts', seamless_api_key: 'contacts',
  email_validation_provider: 'validation', neverbounce_api_key: 'validation',
  zerobounce_api_key: 'validation', hunter_api_key: 'validation', clearout_api_key: 'validation',
  emailable_api_key: 'validation', mailboxvalidator_api_key: 'validation',
  reacher_api_key: 'validation', reacher_base_url: 'validation',
  email_send_mode: 'outreach', smtp_host: 'outreach', smtp_port: 'outreach',
  smtp_user: 'outreach', smtp_password: 'outreach', smtp_from_email: 'outreach',
  smtp_from_name: 'outreach', m365_admin_email: 'outreach', m365_admin_password: 'outreach',
  daily_send_limit: 'business_rules', cooldown_days: 'business_rules',
  max_contacts_per_company_job: 'business_rules', min_salary_threshold: 'business_rules',
  catch_all_policy: 'business_rules', unsubscribe_footer: 'business_rules',
  company_address: 'business_rules', category_window_days: 'business_rules',
  category_regular_threshold: 'business_rules', category_occasional_threshold: 'business_rules',
  data_retention_days: 'business_rules', domain_daily_limit_default: 'business_rules',
  domain_daily_limit_major_providers: 'business_rules', max_contacts_per_company_all_campaigns: 'business_rules',
  send_delay_min_sec: 'business_rules', send_delay_max_sec: 'business_rules',
  // LOB Lead Source API Keys
  google_places_api_key: 'lob_lead_sources', crunchbase_api_key: 'lob_lead_sources',
  builtwith_api_key: 'lob_lead_sources', github_token: 'lob_lead_sources',
  // Source Tuning
  job_source_tuning: 'source_tuning', pipeline_adapter_limit: 'source_tuning',
  pipeline_max_workers: 'source_tuning', posted_within_days: 'source_tuning',
  location_diversification: 'source_tuning', lead_sourcing_target_per_run: 'source_tuning',
  lead_sourcing_max_employee_count: 'source_tuning', lead_sourcing_min_employee_count: 'source_tuning', lead_sourcing_drop_confidential: 'source_tuning',
  lead_sourcing_max_posting_age_days: 'source_tuning', lead_sourcing_drop_expired_postings: 'source_tuning',
  lead_sourcing_scrape_applicants: 'source_tuning', lead_sourcing_max_applicants: 'source_tuning', applicant_scrape_max_lookups: 'source_tuning',
  lead_sourcing_excluded_industries: 'source_tuning', lead_sourcing_enrich_company_at_source: 'source_tuning',
  lead_sourcing_enrich_max_companies: 'source_tuning',
}

// Default out-of-scope industries for the company exclusion gate. Mirrors
// backend company_filters.DEFAULT_EXCLUDED_INDUSTRY_KEYWORDS — shown pre-filled
// so users can edit; clearing the box makes the backend fall back to this list.
const DEFAULT_EXCLUDED_INDUSTRIES = [
  'insurance',
  'information technology', 'it services', 'computer software', 'software development',
  'software', 'saas', 'information services', 'computer hardware', 'computer networking',
  'semiconductor', 'technology, information and internet',
  'staffing', 'recruiting', 'recruitment', 'human resources services', 'employment services',
  'executive search',
  'government administration', 'public administration', 'government relations', 'military',
  'legislative office', 'international affairs',
]

export default function SettingsPage() {
  const router = useRouter()
  const { user } = useAuthStore()
  const isSuperAdmin = user?.role === 'super_admin'
  const isAdmin = user?.role === 'admin' || isSuperAdmin

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
  const [activeTab, setActiveTab] = useState('')
  const [tabPermissions, setTabPermissions] = useState<Record<string, string>>({})
  const [permissionsLoaded, setPermissionsLoaded] = useState(false)

  // Job Source configuration
  const [jobSourceConfig, setJobSourceConfig] = useState<JobSourceConfig>({
    job_source_provider: 'jsearch',
    jsearch_api_key: '',
    indeed_publisher_id: '',
    lead_sources: ['jsearch'],
    enabled_sources: ['linkedin', 'indeed', 'glassdoor', 'simplyhired'],
    target_states: ['CA', 'TX', 'FL', 'NY', 'IL', 'PA', 'OH', 'GA', 'NC', 'MI'],
    available_job_titles: DEFAULT_JOB_TITLES,
    target_job_titles: DEFAULT_JOB_TITLES.slice(0, 16), // First 16 selected by default
    job_title_categories: DEFAULT_JOB_TITLE_CATEGORIES,
    target_industries: TARGET_INDUSTRIES,
    company_size_priority_1_max: 50,
    company_size_priority_2_min: 51,
    company_size_priority_2_max: 500,
    company_size_no_preference: false,
    exclude_it_keywords: DEFAULT_IT_EXCLUSIONS,
    exclude_staffing_keywords: DEFAULT_STAFFING_EXCLUSIONS,
    exclude_company_keywords: DEFAULT_COMPANY_EXCLUSIONS,
    exclude_title_keywords: DEFAULT_TITLE_EXCLUSIONS,
    exclude_match_mode: 'word_boundary',
    lead_sourcing_frequency: '2x',
    location_diversification: false,
    theirstack_api_key: '',
    serpapi_api_key: '',
    adzuna_app_id: '',
    adzuna_api_key: '',
    searchapi_api_key: '',
    usajobs_api_key: '',
    usajobs_email: '',
    jooble_api_key: '',
    jobdatafeeds_api_key: '',
    coresignal_api_key: '',
    fantastic_jobs_api_key: '',
  })

  // State for job title category UI
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set())
  const [titleSearchText, setTitleSearchText] = useState('')
  const [newJobTitle, setNewJobTitle] = useState('')
  const [newJobTitleCategory, setNewJobTitleCategory] = useState('')
  const [categoryDropdownOpen, setCategoryDropdownOpen] = useState(false)
  const [categorySearchText, setCategorySearchText] = useState('')
  const [showCategoryManager, setShowCategoryManager] = useState(false)
  const [newCategoryName, setNewCategoryName] = useState('')
  const [editingCategory, setEditingCategory] = useState<string | null>(null)
  const [editingCategoryName, setEditingCategoryName] = useState('')
  const categoryDropdownRef = useRef<HTMLDivElement>(null)

  // Close category dropdown on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (categoryDropdownRef.current && !categoryDropdownRef.current.contains(e.target as Node)) {
        setCategoryDropdownOpen(false)
        setCategorySearchText('')
      }
    }
    if (categoryDropdownOpen) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [categoryDropdownOpen])

  // State for adding new exclusion keywords
  const [newITKeyword, setNewITKeyword] = useState('')
  const [newStaffingKeyword, setNewStaffingKeyword] = useState('')
  const [newCompanyKeyword, setNewCompanyKeyword] = useState('')
  const [newTitleKeyword, setNewTitleKeyword] = useState('')

  // AI configuration
  const [aiConfig, setAIConfig] = useState<AIConfig>({
    ai_provider: 'groq',
    groq_api_key: '',
    openai_api_key: '',
    anthropic_api_key: '',
    gemini_api_key: '',
    ai_model: 'llama-3.1-70b-versatile',
    ai_personalize_emails: 'yes',
    ai_personalization_prompt: DEFAULT_AI_PERSONALIZATION_PROMPT,
  })

  // Contact configuration
  const [contactConfig, setContactConfig] = useState<ContactConfig>({
    contact_provider: 'mock',
    contact_providers: ['mock'],
    apollo_api_key: '',
    seamless_api_key: '',
    hunter_contact_api_key: '',
    snovio_client_id: '',
    snovio_client_secret: '',
    rocketreach_api_key: '',
    pdl_api_key: '',
    proxycurl_api_key: '',
    clearbit_api_key: '',
    opencorporates_api_key: '',
    company_enrichment_providers: [],
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
    data_retention_days: 180,
    domain_daily_limit_default: 50,
    domain_daily_limit_major_providers: 30,
    max_contacts_per_company_all_campaigns: 5,
    send_delay_min_sec: 45,
    send_delay_max_sec: 180,
  })

  // Deliverability settings
  const [delivConfig, setDelivConfig] = useState({
    complaint_rate_threshold: 0.003,
    domain_daily_limit_default: 50,
    domain_daily_limit_major_providers: 30,
    cooldown_days: 10,
    max_contacts_per_company_all_campaigns: 5,
    sequence_fatigue_window_days: 90,
    sequence_fatigue_max_unanswered: 5,
  })

  // LOB Lead Source API Keys
  const [lobLeadSourceConfig, setLobLeadSourceConfig] = useState({
    google_places_api_key: '',
    crunchbase_api_key: '',
    builtwith_api_key: '',
    github_token: '',
  })

  // Source Tuning config
  const [sourceTuningConfig, setSourceTuningConfig] = useState<{
    job_source_tuning: Record<string, Record<string, number>>;
    pipeline_adapter_limit: number;
    pipeline_max_workers: number;
    posted_within_days: number;
    location_diversification: boolean;
    lead_sourcing_target_per_run: number;
    lead_sourcing_max_employee_count: number;
    lead_sourcing_min_employee_count: number;
    lead_sourcing_max_posting_age_days: number;
    lead_sourcing_drop_expired_postings: boolean;
    lead_sourcing_scrape_applicants: boolean;
    lead_sourcing_max_applicants: number;
    applicant_scrape_max_lookups: number;
    lead_sourcing_drop_confidential: boolean;
    lead_sourcing_excluded_industries: string[];
    lead_sourcing_enrich_company_at_source: boolean;
    lead_sourcing_enrich_max_companies: number;
    target_states: string[];
  }>({
    job_source_tuning: {
      jsearch: { batch_size: 4, num_pages: 10 },
      serpapi: { batch_size: 4, max_pages: 3 },
      searchapi: { batch_size: 4, max_pages: 3 },
      adzuna: { batch_size: 4, max_pages: 10, results_per_page: 50 },
      theirstack: { batch_size: 20, max_pages: 10 },
      usajobs: { batch_size: 2, max_pages: 5, results_per_page: 100 },
      jooble: { batch_size: 4, max_pages: 5 },
      jobdatafeeds: { batch_size: 4, max_pages: 50, results_per_page: 100 },
      coresignal: { batch_size: 5, max_pages: 5, results_per_page: 100 },
    },
    pipeline_adapter_limit: 1000,
    pipeline_max_workers: 6,
    posted_within_days: 7,
    location_diversification: false,
    lead_sourcing_target_per_run: 500,
    lead_sourcing_max_employee_count: 500,
    lead_sourcing_min_employee_count: 1,
    lead_sourcing_max_posting_age_days: 14,
    lead_sourcing_drop_expired_postings: true,
    lead_sourcing_scrape_applicants: false,
    lead_sourcing_max_applicants: 100,
    applicant_scrape_max_lookups: 50,
    lead_sourcing_drop_confidential: true,
    lead_sourcing_excluded_industries: [...DEFAULT_EXCLUDED_INDUSTRIES],
    lead_sourcing_enrich_company_at_source: true,
    lead_sourcing_enrich_max_companies: 300,
    target_states: [...US_STATES],
  })

  // Test results
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message: string }>>({})

  // Company profile (tenant-level)
  const [companyProfile, setCompanyProfile] = useState({ name: '', website: '', industry: '', company_address: '' })
  const [companyProfileLoaded, setCompanyProfileLoaded] = useState(false)
  const [savingProfile, setSavingProfile] = useState(false)

  useEffect(() => {
    loadTabPermissions()
  }, [])

  useEffect(() => {
    if (activeTab === 'business' && !companyProfileLoaded) {
      loadCompanyProfile()
    }
  }, [activeTab])

  const loadTabPermissions = async () => {
    try {
      const perms = await settingsApi.getMySettingsTabPermissions()
      setTabPermissions(perms)
      setPermissionsLoaded(true)

      // Set initial active tab to the first accessible tab
      const tabOrder = ['jobfilters', 'jobsourceapis', 'ai', 'contacts', 'validation', 'outreach', 'business', 'deliverability']
      const firstAccessible = tabOrder.find(tabId => {
        const permKey = TAB_PERM_MAP[tabId]
        return perms[permKey] && perms[permKey] !== 'no_access'
      })
      setActiveTab(firstAccessible || 'jobfilters')

      // Now fetch settings
      await fetchSettings()
    } catch {
      // If permissions endpoint fails, default to super_admin-like access for backwards compat
      const defaultPerms = { job_filters: 'full', job_source_apis: 'full', ai_llm: 'full', contacts: 'full', validation: 'full', outreach: 'full', business_rules: 'full', deliverability: 'full' }
      setTabPermissions(defaultPerms)
      setPermissionsLoaded(true)
      setActiveTab('jobfilters')
      await fetchSettings()
    }
  }

  const getTabAccess = (tabId: string): string => {
    if (isSuperAdmin) return 'full'
    const permKey = TAB_PERM_MAP[tabId]
    if (!permKey) return 'full' // 'all' tab doesn't have its own permission
    return tabPermissions[permKey] || 'no_access'
  }

  const canWriteTab = (tabId: string): boolean => {
    const access = getTabAccess(tabId)
    return access === 'full' || access === 'read_write'
  }

  const canReadTab = (tabId: string): boolean => {
    const access = getTabAccess(tabId)
    return access !== 'no_access'
  }

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
      // Load job title categories (preferred) or derive from flat list
      const storedCategories = settingsMap.job_title_categories
      const categories: Record<string, string[]> = (storedCategories && typeof storedCategories === 'object' && !Array.isArray(storedCategories))
        ? storedCategories
        : DEFAULT_JOB_TITLE_CATEGORIES
      // Derive available titles from categories
      const storedAvailable = settingsMap.available_job_titles || []
      const catTitles = Object.values(categories).flat()
      const mergedAvailable = Array.from(new Set([...catTitles, ...storedAvailable])).sort()

      const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
      setIsLocalhost(isLocal)

      setJobSourceConfig(prev => ({
        ...prev,
        job_source_provider: settingsMap.job_source_provider || 'jsearch',
        jsearch_api_key: settingsMap.jsearch_api_key || '',
        indeed_publisher_id: settingsMap.indeed_publisher_id || '',
        lead_sources: (settingsMap.lead_sources || (isLocal ? ['jsearch', 'mock'] : ['jsearch'])).filter((s: string) => s !== 'apollo'),
        enabled_sources: settingsMap.enabled_sources || ['linkedin', 'indeed', 'glassdoor', 'simplyhired'],
        target_states: settingsMap.target_states || ['CA', 'TX', 'FL', 'NY', 'IL', 'PA', 'OH', 'GA', 'NC', 'MI'],
        available_job_titles: mergedAvailable,
        target_job_titles: settingsMap.target_job_titles || DEFAULT_JOB_TITLES.slice(0, 16),
        job_title_categories: categories,
        target_industries: settingsMap.target_industries || TARGET_INDUSTRIES,
        company_size_priority_1_max: settingsMap.company_size_priority_1_max ?? 50,
        company_size_priority_2_min: settingsMap.company_size_priority_2_min ?? 51,
        company_size_priority_2_max: settingsMap.company_size_priority_2_max ?? 500,
        company_size_no_preference: settingsMap.company_size_no_preference === true,
        exclude_it_keywords: settingsMap.exclude_it_keywords || DEFAULT_IT_EXCLUSIONS,
        exclude_staffing_keywords: settingsMap.exclude_staffing_keywords || DEFAULT_STAFFING_EXCLUSIONS,
        exclude_company_keywords: settingsMap.exclude_company_keywords || DEFAULT_COMPANY_EXCLUSIONS,
        exclude_title_keywords: settingsMap.exclude_title_keywords || DEFAULT_TITLE_EXCLUSIONS,
        exclude_match_mode: settingsMap.exclude_match_mode || 'word_boundary',
        lead_sourcing_frequency: settingsMap.lead_sourcing_frequency || '2x',
        location_diversification: settingsMap.location_diversification === true,
        theirstack_api_key: settingsMap.theirstack_api_key || '',
        serpapi_api_key: settingsMap.serpapi_api_key || '',
        adzuna_app_id: settingsMap.adzuna_app_id || '',
        adzuna_api_key: settingsMap.adzuna_api_key || '',
        searchapi_api_key: settingsMap.searchapi_api_key || '',
        usajobs_api_key: settingsMap.usajobs_api_key || '',
        usajobs_email: settingsMap.usajobs_email || '',
        jooble_api_key: settingsMap.jooble_api_key || '',
        jobdatafeeds_api_key: settingsMap.jobdatafeeds_api_key || '',
        coresignal_api_key: settingsMap.coresignal_api_key || '',
        fantastic_jobs_api_key: settingsMap.fantastic_jobs_api_key || '',
      }))

      setAIConfig(prev => ({
        ...prev,
        ai_provider: settingsMap.ai_provider || 'groq',
        groq_api_key: settingsMap.groq_api_key || '',
        openai_api_key: settingsMap.openai_api_key || '',
        anthropic_api_key: settingsMap.anthropic_api_key || '',
        gemini_api_key: settingsMap.gemini_api_key || '',
        ai_model: settingsMap.ai_model || 'llama-3.1-70b-versatile',
        ai_personalize_emails: settingsMap.ai_personalize_emails || 'yes',
        ai_personalization_prompt: settingsMap.ai_personalization_prompt || DEFAULT_AI_PERSONALIZATION_PROMPT,
      }))

      setContactConfig(prev => ({
        ...prev,
        contact_provider: settingsMap.contact_provider || 'mock',
        contact_providers: settingsMap.contact_providers || (isLocal ? ['mock'] : []),
        apollo_api_key: settingsMap.apollo_api_key || '',
        seamless_api_key: settingsMap.seamless_api_key || '',
        hunter_contact_api_key: settingsMap.hunter_contact_api_key || '',
        snovio_client_id: settingsMap.snovio_client_id || '',
        snovio_client_secret: settingsMap.snovio_client_secret || '',
        rocketreach_api_key: settingsMap.rocketreach_api_key || '',
        pdl_api_key: settingsMap.pdl_api_key || '',
        proxycurl_api_key: settingsMap.proxycurl_api_key || '',
        clearbit_api_key: settingsMap.clearbit_api_key || '',
        opencorporates_api_key: settingsMap.opencorporates_api_key || '',
        company_enrichment_providers: settingsMap.company_enrichment_providers || [],
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
        daily_send_limit: settingsMap.daily_send_limit ?? 30,
        cooldown_days: settingsMap.cooldown_days ?? 10,
        max_contacts_per_company_job: settingsMap.max_contacts_per_company_job ?? 4,
        min_salary_threshold: settingsMap.min_salary_threshold ?? 40000,
        catch_all_policy: settingsMap.catch_all_policy || 'exclude',
        unsubscribe_footer: settingsMap.unsubscribe_footer !== false,
        category_window_days: settingsMap.category_window_days ?? 90,
        category_regular_threshold: settingsMap.category_regular_threshold ?? 3,
        category_occasional_threshold: settingsMap.category_occasional_threshold ?? 0,
        data_retention_days: settingsMap.data_retention_days ?? 180,
        domain_daily_limit_default: settingsMap.domain_daily_limit_default ?? 50,
        domain_daily_limit_major_providers: settingsMap.domain_daily_limit_major_providers ?? 30,
        max_contacts_per_company_all_campaigns: settingsMap.max_contacts_per_company_all_campaigns ?? 5,
        send_delay_min_sec: settingsMap.send_delay_min_sec ?? 45,
        send_delay_max_sec: settingsMap.send_delay_max_sec ?? 180,
      }))
      // Deliverability settings
      setDelivConfig({
        complaint_rate_threshold: settingsMap.complaint_rate_threshold ?? 0.003,
        domain_daily_limit_default: settingsMap.domain_daily_limit_default ?? 50,
        domain_daily_limit_major_providers: settingsMap.domain_daily_limit_major_providers ?? 30,
        cooldown_days: settingsMap.cooldown_days ?? 10,
        max_contacts_per_company_all_campaigns: settingsMap.max_contacts_per_company_all_campaigns ?? 5,
        sequence_fatigue_window_days: settingsMap.sequence_fatigue_window_days ?? 90,
        sequence_fatigue_max_unanswered: settingsMap.sequence_fatigue_max_unanswered ?? 5,
      })

      // LOB Lead Source API Keys
      setLobLeadSourceConfig({
        google_places_api_key: settingsMap.google_places_api_key || '',
        crunchbase_api_key: settingsMap.crunchbase_api_key || '',
        builtwith_api_key: settingsMap.builtwith_api_key || '',
        github_token: settingsMap.github_token || '',
      })

      // Source Tuning
      const defaultTuning = {
        jsearch: { batch_size: 4, num_pages: 10 },
        serpapi: { batch_size: 4, max_pages: 3 },
        searchapi: { batch_size: 4, max_pages: 3 },
        adzuna: { batch_size: 4, max_pages: 10, results_per_page: 50 },
        theirstack: { batch_size: 20, max_pages: 10 },
        usajobs: { batch_size: 2, max_pages: 5, results_per_page: 100 },
        jooble: { batch_size: 4, max_pages: 5 },
        jobdatafeeds: { batch_size: 4, max_pages: 50, results_per_page: 100 },
        coresignal: { batch_size: 5, max_pages: 5, results_per_page: 100 },
      }
      const loadedTuning = settingsMap.job_source_tuning
      // Merge loaded tuning on top of defaults so any new adapter keys are present
      const mergedTuning: Record<string, Record<string, number>> = {}
      for (const [adapter, defaults] of Object.entries(defaultTuning)) {
        mergedTuning[adapter] = { ...(defaults as Record<string, number>), ...(loadedTuning?.[adapter] || {}) }
      }
      setSourceTuningConfig({
        job_source_tuning: mergedTuning,
        pipeline_adapter_limit: settingsMap.pipeline_adapter_limit ?? 1000,
        pipeline_max_workers: settingsMap.pipeline_max_workers ?? 6,
        posted_within_days: settingsMap.posted_within_days ?? 7,
        location_diversification: settingsMap.location_diversification === true,
        lead_sourcing_target_per_run: settingsMap.lead_sourcing_target_per_run ?? 500,
        lead_sourcing_max_employee_count: settingsMap.lead_sourcing_max_employee_count ?? 500,
        lead_sourcing_min_employee_count: settingsMap.lead_sourcing_min_employee_count ?? 1,
        lead_sourcing_max_posting_age_days: settingsMap.lead_sourcing_max_posting_age_days ?? 14,
        lead_sourcing_drop_expired_postings: settingsMap.lead_sourcing_drop_expired_postings !== false,
        lead_sourcing_scrape_applicants: settingsMap.lead_sourcing_scrape_applicants === true,
        lead_sourcing_max_applicants: settingsMap.lead_sourcing_max_applicants ?? 100,
        applicant_scrape_max_lookups: settingsMap.applicant_scrape_max_lookups ?? 50,
        lead_sourcing_drop_confidential: settingsMap.lead_sourcing_drop_confidential !== false,
        lead_sourcing_excluded_industries: (Array.isArray(settingsMap.lead_sourcing_excluded_industries) && settingsMap.lead_sourcing_excluded_industries.length > 0)
          ? settingsMap.lead_sourcing_excluded_industries
          : [...DEFAULT_EXCLUDED_INDUSTRIES],
        lead_sourcing_enrich_company_at_source: settingsMap.lead_sourcing_enrich_company_at_source !== false,
        lead_sourcing_enrich_max_companies: settingsMap.lead_sourcing_enrich_max_companies ?? 300,
        target_states: settingsMap.target_states || [...US_STATES],
      })
    } catch (err: any) {
      if (err.code !== 'ERR_CANCELED') {
        setError(err.response?.data?.detail || 'Failed to fetch settings')
      }
    } finally {
      setLoading(false)
    }
  }

  const loadCompanyProfile = async () => {
    try {
      const data = await settingsApi.getCompanyProfile()
      setCompanyProfile({
        name: data.name || '',
        website: data.website || '',
        industry: data.industry || '',
        company_address: data.company_address || '',
      })
      setCompanyProfileLoaded(true)
    } catch {
      // Non-admin users won't have access — silently ignore
    }
  }

  const saveCompanyProfile = async () => {
    try {
      setSavingProfile(true)
      setError('')
      await settingsApi.updateCompanyProfile(companyProfile)
      setSuccess('Company profile saved!')
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save company profile')
    } finally {
      setSavingProfile(false)
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

      if (configType === 'jobfilters') {
        // Derive available_job_titles from categories for backward compat
        const flatTitles = Array.from(new Set(Object.values(jobSourceConfig.job_title_categories).flat())).sort()
        await Promise.all([
          saveSetting('target_states', jobSourceConfig.target_states, 'list'),
          saveSetting('available_job_titles', flatTitles, 'list'),
          saveSetting('target_job_titles', jobSourceConfig.target_job_titles, 'list'),
          saveSetting('target_industries', jobSourceConfig.target_industries, 'list'),
          saveSetting('company_size_priority_1_max', jobSourceConfig.company_size_priority_1_max, 'integer'),
          saveSetting('company_size_priority_2_min', jobSourceConfig.company_size_priority_2_min, 'integer'),
          saveSetting('company_size_priority_2_max', jobSourceConfig.company_size_priority_2_max, 'integer'),
          saveSetting('company_size_no_preference', jobSourceConfig.company_size_no_preference, 'boolean'),
          saveSetting('exclude_it_keywords', jobSourceConfig.exclude_it_keywords, 'list'),
          saveSetting('exclude_staffing_keywords', jobSourceConfig.exclude_staffing_keywords, 'list'),
          saveSetting('exclude_company_keywords', jobSourceConfig.exclude_company_keywords, 'list'),
          saveSetting('exclude_title_keywords', jobSourceConfig.exclude_title_keywords, 'list'),
          saveSetting('exclude_match_mode', jobSourceConfig.exclude_match_mode),
          saveSetting('job_title_categories', jobSourceConfig.job_title_categories, 'object'),
        ])
      } else if (configType === 'jobsourceapis') {
        await Promise.all([
          saveSetting('job_source_provider', jobSourceConfig.job_source_provider),
          saveSetting('jsearch_api_key', jobSourceConfig.jsearch_api_key),
          saveSetting('indeed_publisher_id', jobSourceConfig.indeed_publisher_id),
          saveSetting('lead_sources', jobSourceConfig.lead_sources, 'list'),
          saveSetting('enabled_sources', jobSourceConfig.enabled_sources, 'list'),
          saveSetting('lead_sourcing_frequency', jobSourceConfig.lead_sourcing_frequency),
          saveSetting('theirstack_api_key', jobSourceConfig.theirstack_api_key),
          saveSetting('serpapi_api_key', jobSourceConfig.serpapi_api_key),
          saveSetting('adzuna_app_id', jobSourceConfig.adzuna_app_id),
          saveSetting('adzuna_api_key', jobSourceConfig.adzuna_api_key),
          saveSetting('searchapi_api_key', jobSourceConfig.searchapi_api_key),
          saveSetting('usajobs_api_key', jobSourceConfig.usajobs_api_key),
          saveSetting('usajobs_email', jobSourceConfig.usajobs_email),
          saveSetting('jooble_api_key', jobSourceConfig.jooble_api_key),
          saveSetting('jobdatafeeds_api_key', jobSourceConfig.jobdatafeeds_api_key),
          saveSetting('coresignal_api_key', jobSourceConfig.coresignal_api_key),
          saveSetting('fantastic_jobs_api_key', jobSourceConfig.fantastic_jobs_api_key),
        ])
      } else if (configType === 'ai') {
        await Promise.all([
          saveSetting('ai_provider', aiConfig.ai_provider),
          saveSetting('groq_api_key', aiConfig.groq_api_key),
          saveSetting('openai_api_key', aiConfig.openai_api_key),
          saveSetting('anthropic_api_key', aiConfig.anthropic_api_key),
          saveSetting('gemini_api_key', aiConfig.gemini_api_key),
          saveSetting('ai_model', aiConfig.ai_model),
          saveSetting('ai_personalize_emails', aiConfig.ai_personalize_emails),
          saveSetting('ai_personalization_prompt', aiConfig.ai_personalization_prompt),
        ])
      } else if (configType === 'contacts') {
        await Promise.all([
          saveSetting('contact_provider', contactConfig.contact_providers[0] || 'mock'),
          saveSetting('contact_providers', contactConfig.contact_providers, 'list'),
          saveSetting('apollo_api_key', contactConfig.apollo_api_key),
          saveSetting('seamless_api_key', contactConfig.seamless_api_key),
          saveSetting('hunter_contact_api_key', contactConfig.hunter_contact_api_key),
          saveSetting('snovio_client_id', contactConfig.snovio_client_id),
          saveSetting('snovio_client_secret', contactConfig.snovio_client_secret),
          saveSetting('rocketreach_api_key', contactConfig.rocketreach_api_key),
          saveSetting('pdl_api_key', contactConfig.pdl_api_key),
          saveSetting('proxycurl_api_key', contactConfig.proxycurl_api_key),
          saveSetting('clearbit_api_key', contactConfig.clearbit_api_key),
          saveSetting('opencorporates_api_key', contactConfig.opencorporates_api_key),
          saveSetting('company_enrichment_providers', contactConfig.company_enrichment_providers, 'list'),
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
          saveSetting('data_retention_days', businessRules.data_retention_days, 'integer'),
          saveSetting('domain_daily_limit_default', businessRules.domain_daily_limit_default, 'integer'),
          saveSetting('domain_daily_limit_major_providers', businessRules.domain_daily_limit_major_providers, 'integer'),
          saveSetting('max_contacts_per_company_all_campaigns', businessRules.max_contacts_per_company_all_campaigns, 'integer'),
          saveSetting('send_delay_min_sec', businessRules.send_delay_min_sec, 'integer'),
          saveSetting('send_delay_max_sec', businessRules.send_delay_max_sec, 'integer'),
        ])
      } else if (configType === 'deliverability') {
        await Promise.all([
          saveSetting('complaint_rate_threshold', delivConfig.complaint_rate_threshold, 'float'),
          saveSetting('domain_daily_limit_default', delivConfig.domain_daily_limit_default, 'integer'),
          saveSetting('domain_daily_limit_major_providers', delivConfig.domain_daily_limit_major_providers, 'integer'),
          saveSetting('cooldown_days', delivConfig.cooldown_days, 'integer'),
          saveSetting('max_contacts_per_company_all_campaigns', delivConfig.max_contacts_per_company_all_campaigns, 'integer'),
          saveSetting('sequence_fatigue_window_days', delivConfig.sequence_fatigue_window_days, 'integer'),
          saveSetting('sequence_fatigue_max_unanswered', delivConfig.sequence_fatigue_max_unanswered, 'integer'),
        ])
      } else if (configType === 'lobleadsources') {
        await Promise.all([
          saveSetting('google_places_api_key', lobLeadSourceConfig.google_places_api_key),
          saveSetting('crunchbase_api_key', lobLeadSourceConfig.crunchbase_api_key),
          saveSetting('builtwith_api_key', lobLeadSourceConfig.builtwith_api_key),
          saveSetting('github_token', lobLeadSourceConfig.github_token),
        ])
      } else if (configType === 'sourcetuning') {
        await Promise.all([
          saveSetting('job_source_tuning', sourceTuningConfig.job_source_tuning, 'object'),
          saveSetting('pipeline_adapter_limit', sourceTuningConfig.pipeline_adapter_limit, 'integer'),
          saveSetting('pipeline_max_workers', sourceTuningConfig.pipeline_max_workers, 'integer'),
          saveSetting('posted_within_days', sourceTuningConfig.posted_within_days, 'integer'),
          saveSetting('location_diversification', sourceTuningConfig.location_diversification, 'boolean'),
          saveSetting('lead_sourcing_target_per_run', sourceTuningConfig.lead_sourcing_target_per_run, 'integer'),
          saveSetting('lead_sourcing_max_employee_count', sourceTuningConfig.lead_sourcing_max_employee_count, 'integer'),
          saveSetting('lead_sourcing_min_employee_count', sourceTuningConfig.lead_sourcing_min_employee_count, 'integer'),
          saveSetting('lead_sourcing_max_posting_age_days', sourceTuningConfig.lead_sourcing_max_posting_age_days, 'integer'),
          saveSetting('lead_sourcing_drop_expired_postings', sourceTuningConfig.lead_sourcing_drop_expired_postings, 'boolean'),
          saveSetting('lead_sourcing_scrape_applicants', sourceTuningConfig.lead_sourcing_scrape_applicants, 'boolean'),
          saveSetting('lead_sourcing_max_applicants', sourceTuningConfig.lead_sourcing_max_applicants, 'integer'),
          saveSetting('applicant_scrape_max_lookups', sourceTuningConfig.applicant_scrape_max_lookups, 'integer'),
          saveSetting('lead_sourcing_drop_confidential', sourceTuningConfig.lead_sourcing_drop_confidential, 'boolean'),
          saveSetting('lead_sourcing_excluded_industries', sourceTuningConfig.lead_sourcing_excluded_industries, 'list'),
          saveSetting('lead_sourcing_enrich_company_at_source', sourceTuningConfig.lead_sourcing_enrich_company_at_source, 'boolean'),
          saveSetting('lead_sourcing_enrich_max_companies', sourceTuningConfig.lead_sourcing_enrich_max_companies, 'integer'),
          saveSetting('target_states', sourceTuningConfig.target_states, 'list'),
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
          { value: 'gpt-4.1-nano', label: 'GPT-4.1 Nano (Cheapest - Recommended)' },
          { value: 'gpt-4.1-mini', label: 'GPT-4.1 Mini (Balanced)' },
          { value: 'gpt-4.1', label: 'GPT-4.1 (Best Quality)' },
          { value: 'gpt-4o-mini', label: 'GPT-4o Mini (Legacy)' },
          { value: 'gpt-4o', label: 'GPT-4o (Legacy)' },
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
            { id: 'jobfilters', label: '1. Job Filters', color: 'indigo' },
            { id: 'jobsourceapis', label: '2. Job Source APIs', color: 'teal' },
            { id: 'ai', label: '3. AI/LLM', color: 'pink' },
            { id: 'contacts', label: '4. Contacts', color: 'purple' },
            { id: 'validation', label: '5. Validation', color: 'cyan' },
            { id: 'outreach', label: '6. Outreach', color: 'orange' },
            { id: 'business', label: '7. Business Rules', color: 'gray' },
            { id: 'deliverability', label: '8. Deliverability', color: 'teal' },
            { id: 'lobleadsources', label: '9. LOB Lead Sources', color: 'emerald' },
            { id: 'sourcetuning', label: '10. Source Tuning', color: 'amber' },
            { id: 'all', label: 'All Settings', color: 'gray' },
          ]
            .filter(tab => {
              if (tab.id === 'all') {
                // Show All Settings if user has access to at least one tab
                return isSuperAdmin || Object.values(tabPermissions).some(v => v !== 'no_access')
              }
              return canReadTab(tab.id)
            })
            .map((tab) => {
              const readOnly = !canWriteTab(tab.id) && tab.id !== 'all'
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`py-3 px-3 border-b-2 font-medium text-sm whitespace-nowrap flex items-center gap-1.5 ${
                    activeTab === tab.id
                      ? `border-${tab.color}-500 text-${tab.color}-600`
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  {tab.label}
                  {readOnly && (
                    <span className="px-1.5 py-0.5 text-[10px] font-medium bg-yellow-100 text-yellow-700 rounded">
                      Read Only
                    </span>
                  )}
                </button>
              )
            })}
        </nav>
      </div>

      {/* Tab 1: Job Filters */}
      {activeTab === 'jobfilters' && (
        <fieldset disabled={!canWriteTab('jobfilters')} className="space-y-6">
          {!canWriteTab('jobfilters') && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm">
              You have read-only access to this tab. Contact a super admin to request edit access.
            </div>
          )}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-indigo-500 rounded-full mr-2"></span>
              Job Filters
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Configure which states, job titles, industries, and company sizes to target for lead sourcing
            </p>

            <div className="space-y-6">
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

              {/* Target Job Titles - Categorized Accordion UI */}
              <div>
                <label className="label">Target Job Titles for Search</label>
                <p className="text-sm text-gray-500 mb-3">
                  Select which job titles to include in lead searches. Titles are organized by category.
                </p>
                {/* "Any" checkbox */}
                <label className="flex items-center gap-2 cursor-pointer mb-3 p-2 rounded-lg border-2 border-dashed border-gray-300 hover:border-blue-400 transition-colors">
                  <input
                    type="checkbox"
                    checked={jobSourceConfig.target_job_titles.length === 1 && jobSourceConfig.target_job_titles[0] === '__ANY__'}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setJobSourceConfig({ ...jobSourceConfig, target_job_titles: ['__ANY__'] })
                      } else {
                        setJobSourceConfig({ ...jobSourceConfig, target_job_titles: DEFAULT_JOB_TITLES.slice(0, 16) })
                      }
                    }}
                    className="w-4 h-4 accent-blue-600"
                  />
                  <span className="text-sm font-semibold text-gray-700">Any</span>
                  <span className="text-xs text-gray-500">— Search all job titles, no title filtering</span>
                </label>
                {!(jobSourceConfig.target_job_titles.length === 1 && jobSourceConfig.target_job_titles[0] === '__ANY__') && (
                <div className="border rounded-lg bg-gray-50">
                  {/* Header with Select All, count, search */}
                  <div className="px-3 py-2 border-b bg-gray-100 rounded-t-lg">
                    <div className="flex items-center justify-between mb-2">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={jobSourceConfig.target_job_titles.length === jobSourceConfig.available_job_titles.length && jobSourceConfig.available_job_titles.length > 0}
                          ref={(el) => {
                            if (el) {
                              const allTitles = jobSourceConfig.available_job_titles
                              const selected = jobSourceConfig.target_job_titles
                              el.indeterminate = selected.length > 0 && selected.length < allTitles.length
                            }
                          }}
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
                          Select All ({jobSourceConfig.target_job_titles.length}/{jobSourceConfig.available_job_titles.length})
                        </span>
                      </label>
                      <button
                        onClick={() => setJobSourceConfig({ ...jobSourceConfig, target_job_titles: [] })}
                        className="text-xs text-gray-600 hover:underline"
                      >
                        Clear All
                      </button>
                    </div>
                    <input
                      type="text"
                      value={titleSearchText}
                      onChange={(e) => setTitleSearchText(e.target.value)}
                      placeholder="Search titles..."
                      className="input text-sm w-full"
                    />
                  </div>
                  {/* Category accordion */}
                  <div className="max-h-96 overflow-y-auto divide-y">
                    {Object.entries(jobSourceConfig.job_title_categories)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([category, titles]) => {
                        const filteredTitles = titleSearchText
                          ? titles.filter(t => t.toLowerCase().includes(titleSearchText.toLowerCase()))
                          : titles
                        // Hide categories with no matching titles when searching
                        if (titleSearchText && filteredTitles.length === 0) return null
                        const isExpanded = expandedCategories.has(category) || (titleSearchText.length > 0 && filteredTitles.length > 0)
                        const selectedInCat = titles.filter(t => jobSourceConfig.target_job_titles.includes(t)).length
                        const totalInCat = titles.length
                        return (
                          <div key={category}>
                            <div className="flex items-center gap-2 px-3 py-2 hover:bg-gray-100 cursor-pointer select-none"
                              onClick={() => {
                                const next = new Set(expandedCategories)
                                if (next.has(category)) next.delete(category); else next.add(category)
                                setExpandedCategories(next)
                              }}>
                              <span className="text-xs text-gray-400 w-4 flex-shrink-0">{isExpanded ? '\u25BC' : '\u25B6'}</span>
                              <input
                                type="checkbox"
                                checked={selectedInCat === totalInCat && totalInCat > 0}
                                ref={(el) => {
                                  if (el) el.indeterminate = selectedInCat > 0 && selectedInCat < totalInCat
                                }}
                                onChange={(e) => {
                                  e.stopPropagation()
                                  if (e.target.checked) {
                                    const newSelected = new Set(jobSourceConfig.target_job_titles)
                                    titles.forEach(t => newSelected.add(t))
                                    setJobSourceConfig({ ...jobSourceConfig, target_job_titles: Array.from(newSelected) })
                                  } else {
                                    setJobSourceConfig({ ...jobSourceConfig, target_job_titles: jobSourceConfig.target_job_titles.filter(t => !titles.includes(t)) })
                                  }
                                }}
                                onClick={(e) => e.stopPropagation()}
                                className="w-4 h-4"
                              />
                              <span className="text-sm font-medium text-gray-700 flex-1">{category}</span>
                              <span className={`text-xs px-1.5 py-0.5 rounded-full ${selectedInCat === totalInCat ? 'bg-blue-100 text-blue-700' : selectedInCat > 0 ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-500'}`}>
                                {selectedInCat}/{totalInCat}
                              </span>
                            </div>
                            {isExpanded && (
                              <div className="pl-10 pr-3 pb-2 flex flex-wrap gap-1.5">
                                {filteredTitles.sort().map(title => (
                                  <label key={title}
                                    className={`flex items-center gap-1.5 cursor-pointer px-2 py-1 rounded border text-xs transition-colors ${
                                      jobSourceConfig.target_job_titles.includes(title)
                                        ? 'bg-blue-50 border-blue-300 text-blue-700'
                                        : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                                    }`}>
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
                                    <span>{title}</span>
                                  </label>
                                ))}
                              </div>
                            )}
                          </div>
                        )
                      })}
                  </div>
                  {/* Add Custom Title with Category Dropdown */}
                  <div className="px-3 py-2 border-t bg-gray-100">
                    <p className="text-xs font-medium text-gray-600 mb-1.5">Add Custom Title</p>
                    <div className="flex gap-2 items-start">
                      {/* Category dropdown */}
                      <div className="relative flex-shrink-0" ref={categoryDropdownRef}>
                        <button
                          type="button"
                          onClick={() => setCategoryDropdownOpen(!categoryDropdownOpen)}
                          className="input text-sm w-44 text-left flex items-center justify-between"
                        >
                          <span className={newJobTitleCategory ? 'text-gray-800' : 'text-gray-400'}>
                            {newJobTitleCategory || 'Category...'}
                          </span>
                          <span className="text-gray-400 text-xs">{categoryDropdownOpen ? '\u25B2' : '\u25BC'}</span>
                        </button>
                        {categoryDropdownOpen && (
                          <div className="absolute z-20 mt-1 w-56 bg-white border rounded-lg shadow-lg max-h-48 overflow-y-auto">
                            <input
                              type="text"
                              value={categorySearchText}
                              onChange={(e) => setCategorySearchText(e.target.value)}
                              placeholder="Search categories..."
                              className="w-full px-3 py-1.5 text-xs border-b outline-none"
                              autoFocus
                            />
                            {Object.keys(jobSourceConfig.job_title_categories)
                              .filter(c => !categorySearchText || c.toLowerCase().includes(categorySearchText.toLowerCase()))
                              .sort()
                              .map(cat => (
                                <button
                                  key={cat}
                                  type="button"
                                  onClick={() => { setNewJobTitleCategory(cat); setCategoryDropdownOpen(false); setCategorySearchText('') }}
                                  className={`w-full text-left px-3 py-1.5 text-xs hover:bg-blue-50 ${newJobTitleCategory === cat ? 'bg-blue-50 text-blue-700' : 'text-gray-700'}`}
                                >
                                  {cat} ({jobSourceConfig.job_title_categories[cat]?.length || 0})
                                </button>
                              ))}
                          </div>
                        )}
                      </div>
                      {/* Title input */}
                      <input
                        type="text"
                        value={newJobTitle}
                        onChange={(e) => setNewJobTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && newJobTitle.trim() && newJobTitleCategory) {
                            e.preventDefault()
                            const title = newJobTitle.trim()
                            const cat = newJobTitleCategory
                            if (!jobSourceConfig.available_job_titles.includes(title)) {
                              const updatedCats = { ...jobSourceConfig.job_title_categories, [cat]: [...(jobSourceConfig.job_title_categories[cat] || []), title] }
                              const flatTitles = Array.from(new Set(Object.values(updatedCats).flat())).sort()
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                job_title_categories: updatedCats,
                                available_job_titles: flatTitles,
                                target_job_titles: [...jobSourceConfig.target_job_titles, title]
                              })
                              setNewJobTitle('')
                            }
                          }
                        }}
                        placeholder="New title..."
                        className="input flex-1 text-sm"
                      />
                      <button
                        onClick={() => {
                          const title = newJobTitle.trim()
                          const cat = newJobTitleCategory
                          if (title && cat && !jobSourceConfig.available_job_titles.includes(title)) {
                            const updatedCats = { ...jobSourceConfig.job_title_categories, [cat]: [...(jobSourceConfig.job_title_categories[cat] || []), title] }
                            const flatTitles = Array.from(new Set(Object.values(updatedCats).flat())).sort()
                            setJobSourceConfig({
                              ...jobSourceConfig,
                              job_title_categories: updatedCats,
                              available_job_titles: flatTitles,
                              target_job_titles: [...jobSourceConfig.target_job_titles, title]
                            })
                            setNewJobTitle('')
                          }
                        }}
                        disabled={!newJobTitle.trim() || !newJobTitleCategory || jobSourceConfig.available_job_titles.includes(newJobTitle.trim())}
                        className="btn-secondary text-sm"
                      >
                        Add
                      </button>
                    </div>
                    <div className="flex items-center justify-between mt-1.5">
                      <p className="text-xs text-gray-500">Select a category, then enter a title</p>
                      <button
                        type="button"
                        onClick={() => setShowCategoryManager(!showCategoryManager)}
                        className="text-xs text-blue-600 hover:underline"
                      >
                        {showCategoryManager ? 'Hide' : 'Manage'} Categories
                      </button>
                    </div>
                  </div>
                  {/* Category Manager */}
                  {showCategoryManager && (
                    <div className="px-3 py-2 border-t bg-white">
                      <p className="text-xs font-medium text-gray-600 mb-2">Manage Categories</p>
                      {/* Add new category */}
                      <div className="flex gap-2 mb-2">
                        <input
                          type="text"
                          value={newCategoryName}
                          onChange={(e) => setNewCategoryName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && newCategoryName.trim() && !jobSourceConfig.job_title_categories[newCategoryName.trim()]) {
                              e.preventDefault()
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                job_title_categories: { ...jobSourceConfig.job_title_categories, [newCategoryName.trim()]: [] }
                              })
                              setNewCategoryName('')
                            }
                          }}
                          placeholder="New category name..."
                          className="input flex-1 text-sm"
                        />
                        <button
                          onClick={() => {
                            if (newCategoryName.trim() && !jobSourceConfig.job_title_categories[newCategoryName.trim()]) {
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                job_title_categories: { ...jobSourceConfig.job_title_categories, [newCategoryName.trim()]: [] }
                              })
                              setNewCategoryName('')
                            }
                          }}
                          disabled={!newCategoryName.trim() || !!jobSourceConfig.job_title_categories[newCategoryName.trim()]}
                          className="btn-secondary text-sm"
                        >
                          Create
                        </button>
                      </div>
                      {/* Category list */}
                      <div className="max-h-48 overflow-y-auto space-y-1">
                        {Object.entries(jobSourceConfig.job_title_categories).sort(([a], [b]) => a.localeCompare(b)).map(([cat, titles]) => (
                          <div key={cat} className="flex items-center gap-2 text-xs py-1 px-1 rounded hover:bg-gray-50 group">
                            {editingCategory === cat ? (
                              <>
                                <input
                                  type="text"
                                  value={editingCategoryName}
                                  onChange={(e) => setEditingCategoryName(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                      const newName = editingCategoryName.trim()
                                      if (newName && newName !== cat && !jobSourceConfig.job_title_categories[newName]) {
                                        const { [cat]: catTitles, ...rest } = jobSourceConfig.job_title_categories
                                        setJobSourceConfig({
                                          ...jobSourceConfig,
                                          job_title_categories: { ...rest, [newName]: catTitles }
                                        })
                                      }
                                      setEditingCategory(null)
                                    } else if (e.key === 'Escape') {
                                      setEditingCategory(null)
                                    }
                                  }}
                                  className="input text-xs flex-1 py-0.5"
                                  autoFocus
                                />
                                <button onClick={() => {
                                  const newName = editingCategoryName.trim()
                                  if (newName && newName !== cat && !jobSourceConfig.job_title_categories[newName]) {
                                    const { [cat]: catTitles, ...rest } = jobSourceConfig.job_title_categories
                                    setJobSourceConfig({
                                      ...jobSourceConfig,
                                      job_title_categories: { ...rest, [newName]: catTitles }
                                    })
                                  }
                                  setEditingCategory(null)
                                }} className="text-green-600 hover:text-green-800">Save</button>
                                <button onClick={() => setEditingCategory(null)} className="text-gray-400 hover:text-gray-600">Cancel</button>
                              </>
                            ) : (
                              <>
                                <span className="flex-1 text-gray-700">{cat}</span>
                                <span className="text-gray-400">({titles.length})</span>
                                <button onClick={() => { setEditingCategory(cat); setEditingCategoryName(cat) }}
                                  className="text-blue-500 hover:text-blue-700 opacity-0 group-hover:opacity-100">Rename</button>
                                <button onClick={() => {
                                  if (confirm(`Delete category "${cat}"? Its ${titles.length} title(s) will be removed from the categories list.`)) {
                                    const { [cat]: _, ...rest } = jobSourceConfig.job_title_categories
                                    const flatTitles = Array.from(new Set(Object.values(rest).flat())).sort()
                                    setJobSourceConfig({
                                      ...jobSourceConfig,
                                      job_title_categories: rest,
                                      available_job_titles: flatTitles,
                                      target_job_titles: jobSourceConfig.target_job_titles.filter(t => flatTitles.includes(t))
                                    })
                                  }
                                }}
                                  className="text-red-500 hover:text-red-700 opacity-0 group-hover:opacity-100">Delete</button>
                              </>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                )}
                {jobSourceConfig.target_job_titles.length === 0 && (
                  <p className="text-xs text-red-500 mt-1">Please select at least one job title for lead searches</p>
                )}
              </div>

            </div>
          </div>

          {/* Target Industries Card */}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-green-500 rounded-full mr-2"></span>
              Target Industries
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Select which industries to target for lead sourcing. Check &quot;Any&quot; to search all industries without filtering.
            </p>
            {/* "Any" checkbox */}
            <label className="flex items-center gap-2 cursor-pointer mb-3 p-2 rounded-lg border-2 border-dashed border-gray-300 hover:border-green-400 transition-colors">
              <input
                type="checkbox"
                checked={jobSourceConfig.target_industries.length === 1 && jobSourceConfig.target_industries[0] === '__ANY__'}
                onChange={(e) => {
                  if (e.target.checked) {
                    setJobSourceConfig({ ...jobSourceConfig, target_industries: ['__ANY__'] })
                  } else {
                    setJobSourceConfig({ ...jobSourceConfig, target_industries: [...TARGET_INDUSTRIES] })
                  }
                }}
                className="w-4 h-4 accent-green-600"
              />
              <span className="text-sm font-semibold text-gray-700">Any</span>
              <span className="text-xs text-gray-500">— Search all industries, no industry filtering</span>
            </label>
            {!(jobSourceConfig.target_industries.length === 1 && jobSourceConfig.target_industries[0] === '__ANY__') && (
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
            )}
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
            {/* No Preference checkbox */}
            <label className="flex items-center gap-2 cursor-pointer mb-4 p-2 rounded-lg border-2 border-dashed border-gray-300 hover:border-blue-400 transition-colors">
              <input
                type="checkbox"
                checked={jobSourceConfig.company_size_no_preference}
                onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, company_size_no_preference: e.target.checked })}
                className="w-4 h-4 accent-blue-600"
              />
              <span className="text-sm font-semibold text-gray-700">No Preference</span>
              <span className="text-xs text-gray-500">— Accept all company sizes, no priority matching</span>
            </label>
            <div className={`grid grid-cols-1 sm:grid-cols-3 gap-4 ${jobSourceConfig.company_size_no_preference ? 'opacity-50 pointer-events-none' : ''}`}>
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                <h4 className="font-medium text-green-700 mb-2">Priority 1 (Preferred)</h4>
                <label className="label text-sm">Max Employees</label>
                <input
                  type="number"
                  value={jobSourceConfig.company_size_priority_1_max}
                  onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, company_size_priority_1_max: parseInt(e.target.value) || 50 })}
                  className="input"
                  min="1"
                  disabled={jobSourceConfig.company_size_no_preference}
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
                  disabled={jobSourceConfig.company_size_no_preference}
                />
                <label className="label text-sm">Max Employees</label>
                <input
                  type="number"
                  value={jobSourceConfig.company_size_priority_2_max}
                  onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, company_size_priority_2_max: parseInt(e.target.value) || 500 })}
                  className="input"
                  min="1"
                  disabled={jobSourceConfig.company_size_no_preference}
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

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
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

              {/* Company Name Exclusions */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="label mb-0">
                    <span>Company Name Exclusions</span>
                    <span className="text-xs text-gray-500 ml-2">
                      ({jobSourceConfig.exclude_company_keywords.length} active)
                    </span>
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        if (jobSourceConfig.exclude_company_keywords.length === 0) {
                          setJobSourceConfig({ ...jobSourceConfig, exclude_company_keywords: DEFAULT_COMPANY_EXCLUSIONS })
                        } else {
                          setJobSourceConfig({ ...jobSourceConfig, exclude_company_keywords: [] })
                        }
                      }}
                      className="text-xs text-blue-600 hover:text-blue-800 underline"
                    >
                      {jobSourceConfig.exclude_company_keywords.length === 0 ? 'Check All' : 'Uncheck All'}
                    </button>
                    <button
                      onClick={() => setJobSourceConfig({ ...jobSourceConfig, exclude_company_keywords: [...DEFAULT_COMPANY_EXCLUSIONS] })}
                      className="text-xs text-gray-500 hover:text-gray-700 underline"
                    >
                      Reset Defaults
                    </button>
                  </div>
                </div>
                <div className="border border-gray-200 rounded-lg p-3 max-h-48 overflow-y-auto bg-white">
                  <div className="flex flex-wrap gap-2">
                    {Array.from(new Set([...jobSourceConfig.exclude_company_keywords, ...DEFAULT_COMPANY_EXCLUSIONS])).sort().map((keyword) => {
                      const isActive = jobSourceConfig.exclude_company_keywords.includes(keyword)
                      const isDefault = DEFAULT_COMPANY_EXCLUSIONS.includes(keyword)
                      return (
                        <div
                          key={keyword}
                          className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs cursor-pointer transition-all ${
                            isActive
                              ? 'bg-orange-100 text-orange-800 border border-orange-300'
                              : 'bg-gray-100 text-gray-400 border border-gray-200 line-through'
                          }`}
                          onClick={() => {
                            if (isActive) {
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                exclude_company_keywords: jobSourceConfig.exclude_company_keywords.filter(k => k !== keyword)
                              })
                            } else {
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                exclude_company_keywords: [...jobSourceConfig.exclude_company_keywords, keyword]
                              })
                            }
                          }}
                        >
                          <input type="checkbox" checked={isActive} onChange={() => {}} className="w-3 h-3 cursor-pointer" />
                          <span>{keyword}</span>
                          {!isDefault && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                setJobSourceConfig({
                                  ...jobSourceConfig,
                                  exclude_company_keywords: jobSourceConfig.exclude_company_keywords.filter(k => k !== keyword)
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
                    value={newCompanyKeyword}
                    onChange={(e) => setNewCompanyKeyword(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newCompanyKeyword.trim()) {
                        const kw = newCompanyKeyword.trim().toLowerCase()
                        if (!jobSourceConfig.exclude_company_keywords.includes(kw)) {
                          setJobSourceConfig({
                            ...jobSourceConfig,
                            exclude_company_keywords: [...jobSourceConfig.exclude_company_keywords, kw]
                          })
                        }
                        setNewCompanyKeyword('')
                      }
                    }}
                    placeholder="Add custom keyword..."
                    className="input text-xs flex-1"
                  />
                  <button
                    onClick={() => {
                      const kw = newCompanyKeyword.trim().toLowerCase()
                      if (kw && !jobSourceConfig.exclude_company_keywords.includes(kw)) {
                        setJobSourceConfig({
                          ...jobSourceConfig,
                          exclude_company_keywords: [...jobSourceConfig.exclude_company_keywords, kw]
                        })
                      }
                      setNewCompanyKeyword('')
                    }}
                    className="btn-secondary text-xs px-3"
                  >
                    Add
                  </button>
                </div>
                <p className="text-xs text-gray-400 mt-1">Matched only against company name. Use for staffing agencies and similar.</p>
              </div>

              {/* Job Title Exclusions */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="label mb-0">
                    <span>Job Title Exclusions</span>
                    <span className="text-xs text-gray-500 ml-2">
                      ({jobSourceConfig.exclude_title_keywords.length} active)
                    </span>
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        if (jobSourceConfig.exclude_title_keywords.length === 0) {
                          setJobSourceConfig({ ...jobSourceConfig, exclude_title_keywords: DEFAULT_TITLE_EXCLUSIONS })
                        } else {
                          setJobSourceConfig({ ...jobSourceConfig, exclude_title_keywords: [] })
                        }
                      }}
                      className="text-xs text-blue-600 hover:text-blue-800 underline"
                    >
                      {jobSourceConfig.exclude_title_keywords.length === 0 ? 'Check All' : 'Uncheck All'}
                    </button>
                    <button
                      onClick={() => setJobSourceConfig({ ...jobSourceConfig, exclude_title_keywords: [...DEFAULT_TITLE_EXCLUSIONS] })}
                      className="text-xs text-gray-500 hover:text-gray-700 underline"
                    >
                      Reset Defaults
                    </button>
                  </div>
                </div>
                <div className="border border-gray-200 rounded-lg p-3 max-h-48 overflow-y-auto bg-white">
                  <div className="flex flex-wrap gap-2">
                    {Array.from(new Set([...jobSourceConfig.exclude_title_keywords, ...DEFAULT_TITLE_EXCLUSIONS])).sort().map((keyword) => {
                      const isActive = jobSourceConfig.exclude_title_keywords.includes(keyword)
                      const isDefault = DEFAULT_TITLE_EXCLUSIONS.includes(keyword)
                      return (
                        <div
                          key={keyword}
                          className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs cursor-pointer transition-all ${
                            isActive
                              ? 'bg-purple-100 text-purple-800 border border-purple-300'
                              : 'bg-gray-100 text-gray-400 border border-gray-200 line-through'
                          }`}
                          onClick={() => {
                            if (isActive) {
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                exclude_title_keywords: jobSourceConfig.exclude_title_keywords.filter(k => k !== keyword)
                              })
                            } else {
                              setJobSourceConfig({
                                ...jobSourceConfig,
                                exclude_title_keywords: [...jobSourceConfig.exclude_title_keywords, keyword]
                              })
                            }
                          }}
                        >
                          <input type="checkbox" checked={isActive} onChange={() => {}} className="w-3 h-3 cursor-pointer" />
                          <span>{keyword}</span>
                          {!isDefault && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                setJobSourceConfig({
                                  ...jobSourceConfig,
                                  exclude_title_keywords: jobSourceConfig.exclude_title_keywords.filter(k => k !== keyword)
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
                    value={newTitleKeyword}
                    onChange={(e) => setNewTitleKeyword(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && newTitleKeyword.trim()) {
                        const kw = newTitleKeyword.trim().toLowerCase()
                        if (!jobSourceConfig.exclude_title_keywords.includes(kw)) {
                          setJobSourceConfig({
                            ...jobSourceConfig,
                            exclude_title_keywords: [...jobSourceConfig.exclude_title_keywords, kw]
                          })
                        }
                        setNewTitleKeyword('')
                      }
                    }}
                    placeholder="Add custom keyword..."
                    className="input text-xs flex-1"
                  />
                  <button
                    onClick={() => {
                      const kw = newTitleKeyword.trim().toLowerCase()
                      if (kw && !jobSourceConfig.exclude_title_keywords.includes(kw)) {
                        setJobSourceConfig({
                          ...jobSourceConfig,
                          exclude_title_keywords: [...jobSourceConfig.exclude_title_keywords, kw]
                        })
                      }
                      setNewTitleKeyword('')
                    }}
                    className="btn-secondary text-xs px-3"
                  >
                    Add
                  </button>
                </div>
                <p className="text-xs text-gray-400 mt-1">Matched only against job title. Use for intern, entry-level roles, etc.</p>
              </div>

              {/* Keyword Matching Mode */}
              <div>
                <label className="label">Keyword Matching Mode</label>
                <div className="flex gap-3">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="matchMode"
                      value="word_boundary"
                      checked={jobSourceConfig.exclude_match_mode === 'word_boundary'}
                      onChange={() => setJobSourceConfig({ ...jobSourceConfig, exclude_match_mode: 'word_boundary' })}
                      className="w-4 h-4"
                    />
                    <span className="text-sm">Word Boundary (Recommended)</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="matchMode"
                      value="substring"
                      checked={jobSourceConfig.exclude_match_mode === 'substring'}
                      onChange={() => setJobSourceConfig({ ...jobSourceConfig, exclude_match_mode: 'substring' })}
                      className="w-4 h-4"
                    />
                    <span className="text-sm">Substring</span>
                  </label>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  Word boundary prevents &quot;intern&quot; from matching &quot;international&quot;. Substring matches any occurrence within text.
                </p>
              </div>
            </div>
          </div>

          {canWriteTab('jobfilters') && (
            <div className="flex justify-end">
              <button onClick={() => saveAllSettings('jobfilters')} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save Job Filter Settings'}
              </button>
            </div>
          )}
        </fieldset>
      )}

      {/* Tab 2: Job Source APIs */}
      {activeTab === 'jobsourceapis' && (
        <fieldset disabled={!canWriteTab('jobsourceapis')} className="space-y-6">
          {!canWriteTab('jobsourceapis') && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm">
              You have read-only access to this tab. Contact a super admin to request edit access.
            </div>
          )}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-teal-500 rounded-full mr-2"></span>
              Job Source APIs
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Configure where to fetch job postings from (LinkedIn, Indeed, Glassdoor, etc.) and manage API keys
            </p>

            <div className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
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

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                  <div>
                    <label className="label">Enabled Lead Sources</label>
                    <div className="space-y-2 border rounded-lg p-3 bg-gray-50">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('jsearch')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'jsearch'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter(s => s !== 'jsearch') }) } }} className="w-4 h-4" />
                        <span className="text-sm font-medium">JSearch (LinkedIn, Indeed, Glassdoor)</span>
                        <span className="text-xs text-gray-400">Free: 500 req/mo | Paid: from $50/mo</span>
                        {jobSourceConfig.jsearch_api_key && <span className="text-xs text-green-600">API key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('theirstack')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'theirstack'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter(s => s !== 'theirstack') }) } }} className="w-4 h-4" />
                        <span className="text-sm font-medium">TheirStack (Tech Stack Jobs)</span>
                        <span className="text-xs text-gray-400">Free: 100 req/mo | Paid: from $49/mo</span>
                        {jobSourceConfig.theirstack_api_key && <span className="text-xs text-green-600">API key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('serpapi')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'serpapi'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter(s => s !== 'serpapi') }) } }} className="w-4 h-4" />
                        <span className="text-sm font-medium">SerpAPI (Google Jobs)</span>
                        <span className="text-xs text-gray-400">Free: 100 req/mo | Paid: from $50/mo</span>
                        {jobSourceConfig.serpapi_api_key && <span className="text-xs text-green-600">API key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('adzuna')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'adzuna'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter(s => s !== 'adzuna') }) } }} className="w-4 h-4" />
                        <span className="text-sm font-medium">Adzuna (Job Aggregator)</span>
                        <span className="text-xs text-gray-400">Free: 250 req/mo | Paid: from $99/mo</span>
                        {jobSourceConfig.adzuna_app_id && jobSourceConfig.adzuna_api_key && <span className="text-xs text-green-600">Credentials configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('searchapi')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'searchapi'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter((s: string) => s !== 'searchapi') }) } }} className="w-4 h-4" />
                        <span className="text-sm font-medium">SearchAPI.io (Google Jobs)</span>
                        <span className="text-xs text-gray-500">$40/mo</span>
                        {jobSourceConfig.searchapi_api_key && <span className="text-xs text-green-600">Key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('usajobs')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'usajobs'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter((s: string) => s !== 'usajobs') }) } }} className="w-4 h-4" />
                        <span className="text-sm font-medium">USAJOBS (Federal)</span>
                        <span className="text-xs text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded">Free</span>
                        {jobSourceConfig.usajobs_api_key && <span className="text-xs text-green-600">Key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('jooble')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'jooble'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter((s: string) => s !== 'jooble') }) } }} className="w-4 h-4" />
                        <span className="text-sm font-medium">Jooble (71 Countries)</span>
                        <span className="text-xs text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded">Free</span>
                        {jobSourceConfig.jooble_api_key && <span className="text-xs text-green-600">Key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('jobdatafeeds')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'jobdatafeeds'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter((s: string) => s !== 'jobdatafeeds') }) } }} className="w-4 h-4" />
                        <span className="text-sm font-medium">JobDataFeeds (Bulk US)</span>
                        <span className="text-xs text-gray-500">$200-400/mo</span>
                        {jobSourceConfig.jobdatafeeds_api_key && <span className="text-xs text-green-600">Key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('coresignal')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'coresignal'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter((s: string) => s !== 'coresignal') }) } }} className="w-4 h-4" />
                        <span className="text-sm font-medium">Coresignal (Jobs + Contacts)</span>
                        <span className="text-xs text-gray-400">Contact-based pricing</span>
                        <span className="text-xs text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded">Premium</span>
                        {jobSourceConfig.coresignal_api_key && <span className="text-xs text-green-600">Key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('fantastic_jobs')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'fantastic_jobs'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter((s: string) => s !== 'fantastic_jobs') }) } }} className="w-4 h-4" />
                        <span className="text-sm font-medium">Fantastic.jobs (LinkedIn + Firmographics)</span>
                        <span className="text-xs text-gray-500">from $95/mo</span>
                        {jobSourceConfig.fantastic_jobs_api_key && <span className="text-xs text-green-600">Key configured</span>}
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={jobSourceConfig.lead_sources.includes('mock')} onChange={(e) => { if (e.target.checked) { setJobSourceConfig({ ...jobSourceConfig, lead_sources: [...jobSourceConfig.lead_sources, 'mock'] }) } else { setJobSourceConfig({ ...jobSourceConfig, lead_sources: jobSourceConfig.lead_sources.filter(s => s !== 'mock') }) } }} className="w-4 h-4" />
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

                  {/* TheirStack API Key */}
                  {jobSourceConfig.lead_sources.includes('theirstack') && (
                    <div>
                      <label className="label">TheirStack API Key</label>
                      <div className="flex gap-2">
                        <input type="password" value={jobSourceConfig.theirstack_api_key} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, theirstack_api_key: e.target.value })} placeholder="Enter TheirStack API key" className="input flex-1" />
                        <button onClick={() => testConnection('theirstack')} disabled={testing === 'theirstack' || !jobSourceConfig.theirstack_api_key} className="btn-secondary text-sm">{testing === 'theirstack' ? 'Testing...' : 'Test'}</button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Get key at <a href="https://theirstack.com/" target="_blank" className="text-blue-600 underline">theirstack.com</a> — Free: 100 req/mo | Paid: from $49/mo</p>
                      {testResults.theirstack && <p className={`text-sm mt-1 ${testResults.theirstack.success ? 'text-green-600' : 'text-red-600'}`}>{testResults.theirstack.message}</p>}
                    </div>
                  )}

                  {/* SerpAPI Key */}
                  {jobSourceConfig.lead_sources.includes('serpapi') && (
                    <div>
                      <label className="label">SerpAPI Key (Google Jobs)</label>
                      <div className="flex gap-2">
                        <input type="password" value={jobSourceConfig.serpapi_api_key} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, serpapi_api_key: e.target.value })} placeholder="Enter SerpAPI key" className="input flex-1" />
                        <button onClick={() => testConnection('serpapi')} disabled={testing === 'serpapi' || !jobSourceConfig.serpapi_api_key} className="btn-secondary text-sm">{testing === 'serpapi' ? 'Testing...' : 'Test'}</button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Get key at <a href="https://serpapi.com/" target="_blank" className="text-blue-600 underline">serpapi.com</a> — Free: 100 req/mo | Paid: from $50/mo</p>
                      {testResults.serpapi && <p className={`text-sm mt-1 ${testResults.serpapi.success ? 'text-green-600' : 'text-red-600'}`}>{testResults.serpapi.message}</p>}
                    </div>
                  )}

                  {/* Adzuna Credentials */}
                  {jobSourceConfig.lead_sources.includes('adzuna') && (
                    <div>
                      <label className="label">Adzuna App ID</label>
                      <input type="text" value={jobSourceConfig.adzuna_app_id} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, adzuna_app_id: e.target.value })} placeholder="Enter Adzuna App ID" className="input w-full mb-2" />
                      <label className="label">Adzuna API Key</label>
                      <div className="flex gap-2">
                        <input type="password" value={jobSourceConfig.adzuna_api_key} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, adzuna_api_key: e.target.value })} placeholder="Enter Adzuna API key" className="input flex-1" />
                        <button onClick={() => testConnection('adzuna')} disabled={testing === 'adzuna' || !jobSourceConfig.adzuna_app_id || !jobSourceConfig.adzuna_api_key} className="btn-secondary text-sm">{testing === 'adzuna' ? 'Testing...' : 'Test'}</button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Get credentials at <a href="https://developer.adzuna.com/" target="_blank" className="text-blue-600 underline">developer.adzuna.com</a> — Free: 250 req/mo | Paid: from $99/mo</p>
                      {testResults.adzuna && <p className={`text-sm mt-1 ${testResults.adzuna.success ? 'text-green-600' : 'text-red-600'}`}>{testResults.adzuna.message}</p>}
                    </div>
                  )}

                  {/* SearchAPI Key */}
                  {jobSourceConfig.lead_sources.includes('searchapi') && (
                    <div>
                      <label className="label">SearchAPI.io API Key</label>
                      <div className="flex gap-2">
                        <input type="password" value={jobSourceConfig.searchapi_api_key} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, searchapi_api_key: e.target.value })} placeholder="Enter SearchAPI.io key" className="input flex-1" />
                        <button onClick={() => testConnection('searchapi')} disabled={testing === 'searchapi' || !jobSourceConfig.searchapi_api_key} className="btn-secondary text-sm">{testing === 'searchapi' ? 'Testing...' : 'Test'}</button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Get key at <a href="https://www.searchapi.io/" target="_blank" className="text-blue-600 underline">searchapi.io</a> — Google Jobs data at $40/mo</p>
                      {testResults.searchapi && <p className={`text-sm mt-1 ${testResults.searchapi.success ? 'text-green-600' : 'text-red-600'}`}>{testResults.searchapi.message}</p>}
                    </div>
                  )}

                  {/* USAJOBS Credentials */}
                  {jobSourceConfig.lead_sources.includes('usajobs') && (
                    <div>
                      <label className="label">USAJOBS API Key</label>
                      <input type="password" value={jobSourceConfig.usajobs_api_key} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, usajobs_api_key: e.target.value })} placeholder="Enter USAJOBS API key" className="input w-full mb-2" />
                      <label className="label">USAJOBS Email (User-Agent)</label>
                      <div className="flex gap-2">
                        <input type="text" value={jobSourceConfig.usajobs_email} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, usajobs_email: e.target.value })} placeholder="your-email@example.com" className="input flex-1" />
                        <button onClick={() => testConnection('usajobs')} disabled={testing === 'usajobs' || !jobSourceConfig.usajobs_api_key} className="btn-secondary text-sm">{testing === 'usajobs' ? 'Testing...' : 'Test'}</button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Get free API key at <a href="https://developer.usajobs.gov/" target="_blank" className="text-blue-600 underline">developer.usajobs.gov</a> — US federal jobs, completely free</p>
                      {testResults.usajobs && <p className={`text-sm mt-1 ${testResults.usajobs.success ? 'text-green-600' : 'text-red-600'}`}>{testResults.usajobs.message}</p>}
                    </div>
                  )}

                  {/* Jooble Key */}
                  {jobSourceConfig.lead_sources.includes('jooble') && (
                    <div>
                      <label className="label">Jooble API Key</label>
                      <div className="flex gap-2">
                        <input type="password" value={jobSourceConfig.jooble_api_key} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, jooble_api_key: e.target.value })} placeholder="Enter Jooble API key" className="input flex-1" />
                        <button onClick={() => testConnection('jooble')} disabled={testing === 'jooble' || !jobSourceConfig.jooble_api_key} className="btn-secondary text-sm">{testing === 'jooble' ? 'Testing...' : 'Test'}</button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Get free key at <a href="https://jooble.org/api/about" target="_blank" className="text-blue-600 underline">jooble.org/api</a> — 71-country aggregator, free</p>
                      {testResults.jooble && <p className={`text-sm mt-1 ${testResults.jooble.success ? 'text-green-600' : 'text-red-600'}`}>{testResults.jooble.message}</p>}
                    </div>
                  )}

                  {/* JobDataFeeds Key */}
                  {jobSourceConfig.lead_sources.includes('jobdatafeeds') && (
                    <div>
                      <label className="label">JobDataFeeds API Key</label>
                      <div className="flex gap-2">
                        <input type="password" value={jobSourceConfig.jobdatafeeds_api_key} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, jobdatafeeds_api_key: e.target.value })} placeholder="Enter JobDataFeeds API key" className="input flex-1" />
                        <button onClick={() => testConnection('jobdatafeeds')} disabled={testing === 'jobdatafeeds' || !jobSourceConfig.jobdatafeeds_api_key} className="btn-secondary text-sm">{testing === 'jobdatafeeds' ? 'Testing...' : 'Test'}</button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Sign up at <a href="https://jobdatafeeds.com/" target="_blank" className="text-blue-600 underline">jobdatafeeds.com</a> — Bulk US jobs ~$1/1,000 jobs ($200-400/mo)</p>
                      {testResults.jobdatafeeds && <p className={`text-sm mt-1 ${testResults.jobdatafeeds.success ? 'text-green-600' : 'text-red-600'}`}>{testResults.jobdatafeeds.message}</p>}
                    </div>
                  )}

                  {/* Coresignal Key */}
                  {jobSourceConfig.lead_sources.includes('coresignal') && (
                    <div>
                      <label className="label">Coresignal API Key</label>
                      <div className="flex gap-2">
                        <input type="password" value={jobSourceConfig.coresignal_api_key} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, coresignal_api_key: e.target.value })} placeholder="Enter Coresignal API key" className="input flex-1" />
                        <button onClick={() => testConnection('coresignal')} disabled={testing === 'coresignal' || !jobSourceConfig.coresignal_api_key} className="btn-secondary text-sm">{testing === 'coresignal' ? 'Testing...' : 'Test'}</button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Sign up at <a href="https://coresignal.com/" target="_blank" className="text-blue-600 underline">coresignal.com</a> — 399M+ jobs with recruiter contacts ($800-1,500/mo)</p>
                      {testResults.coresignal && <p className={`text-sm mt-1 ${testResults.coresignal.success ? 'text-green-600' : 'text-red-600'}`}>{testResults.coresignal.message}</p>}
                    </div>
                  )}

                  {/* Fantastic.jobs Key */}
                  {jobSourceConfig.lead_sources.includes('fantastic_jobs') && (
                    <div>
                      <label className="label">Fantastic.jobs API Key</label>
                      <div className="flex gap-2">
                        <input type="password" value={jobSourceConfig.fantastic_jobs_api_key} onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, fantastic_jobs_api_key: e.target.value })} placeholder="Enter Fantastic.jobs (Bearer) API key" className="input flex-1" />
                        <button onClick={() => testConnection('fantastic_jobs')} disabled={testing === 'fantastic_jobs' || !jobSourceConfig.fantastic_jobs_api_key} className="btn-secondary text-sm">{testing === 'fantastic_jobs' ? 'Testing...' : 'Test'}</button>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Direct API key from <a href="https://fantastic.jobs/api" target="_blank" className="text-blue-600 underline">fantastic.jobs/api</a> — LinkedIn feed with company firmographics (7-day trial; plans from $95/mo)</p>
                      {testResults.fantastic_jobs && <p className={`text-sm mt-1 ${testResults.fantastic_jobs.success ? 'text-green-600' : 'text-red-600'}`}>{testResults.fantastic_jobs.message}</p>}
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

                {/* Pipeline Scheduler */}
                <div className="mt-6 border-t pt-4">
                  <h4 className="text-sm font-semibold text-gray-700 flex items-center mb-3">
                    <span className="w-2 h-2 bg-blue-500 rounded-full mr-2"></span>
                    Pipeline Scheduler
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="label">Frequency</label>
                      <select
                        value={jobSourceConfig.lead_sourcing_frequency}
                        onChange={(e) => setJobSourceConfig({ ...jobSourceConfig, lead_sourcing_frequency: e.target.value as '2x' | '4x' | '6x' })}
                        className="input"
                      >
                        <option value="2x">2x/day (6 AM, 6 PM UTC)</option>
                        <option value="4x">4x/day (every 6 hours)</option>
                        <option value="6x">6x/day (every 4 hours)</option>
                      </select>
                      <p className="text-xs text-gray-500 mt-1">Lower frequency preserves API quota. 2x/day is recommended for free-tier API keys.</p>
                    </div>
                  </div>
                </div>

                {/* Location Strategy — moved to Source Tuning */}
                <div className="mt-6 border-t pt-4">
                  <h4 className="text-sm font-semibold text-gray-700 flex items-center mb-3">
                    <span className="w-2 h-2 bg-amber-500 rounded-full mr-2"></span>
                    Location Strategy
                  </h4>
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <p className="text-sm text-blue-800">
                      Location diversification and posted-within-days settings have moved to the <button
                        type="button"
                        onClick={() => setActiveTab('sourcetuning')}
                        className="font-semibold underline hover:text-blue-900"
                      >Source Tuning</button> tab for centralized pipeline configuration.
                    </p>
                  </div>
                </div>
              </div>

              {jobSourceConfig.job_source_provider === 'mock' && (
                <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="text-sm text-yellow-700">
                    <strong>Mock Mode:</strong> Using simulated job data. For real job postings, configure JSearch API (recommended) or Indeed Publisher API.
                  </p>
                </div>
              )}

              {/* Enabled Sub-Sources */}
              <div className="border-t pt-6 mt-6">
                <h4 className="font-medium text-gray-700 mb-3 flex items-center">
                  <span className="w-2 h-2 bg-indigo-500 rounded-full mr-2"></span>
                  Enabled Sub-Sources (per JSearch)
                </h4>
                <p className="text-sm text-gray-500 mb-3">
                  Select which job boards to include when JSearch fetches results.
                </p>
                <div className="flex flex-wrap gap-3">
                  {['linkedin', 'indeed', 'glassdoor', 'simplyhired', 'ziprecruiter'].map((source) => (
                    <label key={source} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={jobSourceConfig.enabled_sources.includes(source)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setJobSourceConfig({ ...jobSourceConfig, enabled_sources: [...jobSourceConfig.enabled_sources, source] })
                          } else {
                            setJobSourceConfig({ ...jobSourceConfig, enabled_sources: jobSourceConfig.enabled_sources.filter(s => s !== source) })
                          }
                        }}
                        className="w-4 h-4"
                      />
                      <span className="text-sm capitalize">{source}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {canWriteTab('jobsourceapis') && (
            <div className="flex justify-end">
              <button onClick={() => saveAllSettings('jobsourceapis')} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save Job Source API Settings'}
              </button>
            </div>
          )}
        </fieldset>
      )}

      {/* Tab 3: AI/LLM */}
      {activeTab === 'ai' && (
        <fieldset disabled={!canWriteTab('ai')} className="space-y-6">
          {!canWriteTab('ai') && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm">
              You have read-only access to this tab. Contact a super admin to request edit access.
            </div>
          )}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-pink-500 rounded-full mr-2"></span>
              AI / LLM Configuration
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Configure AI provider for email content generation, lead qualification, and other AI-powered features
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
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
                  <option value="openai">OpenAI</option>
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
                  {testResults.openai && (
                    <p className={`text-sm mt-1 ${testResults.openai.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.openai.message}
                    </p>
                  )}
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
                  {testResults.anthropic && (
                    <p className={`text-sm mt-1 ${testResults.anthropic.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.anthropic.message}
                    </p>
                  )}
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
                  {testResults.gemini && (
                    <p className={`text-sm mt-1 ${testResults.gemini.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.gemini.message}
                    </p>
                  )}
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

            {/* AI Email Personalization */}
            <div className="mt-6 pt-6 border-t border-gray-200">
              <h4 className="font-semibold text-gray-800 mb-1">AI Email Personalization</h4>
              <p className="text-sm text-gray-500 mb-4">
                When enabled, each outreach email is rewritten by AI at send time using the contact&apos;s profile to create unique, human-sounding variations.
              </p>

              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">Enable AI Personalization</label>
                <select
                  className="input-field w-48"
                  value={aiConfig.ai_personalize_emails}
                  onChange={(e) => setAIConfig({ ...aiConfig, ai_personalize_emails: e.target.value })}
                >
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </div>

              {aiConfig.ai_personalize_emails === 'yes' && (
                <div className="space-y-3">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-sm font-medium text-gray-700">Personalization Prompt</label>
                      <button
                        type="button"
                        className="text-xs text-blue-600 hover:text-blue-800"
                        onClick={() => setAIConfig({ ...aiConfig, ai_personalization_prompt: DEFAULT_AI_PERSONALIZATION_PROMPT })}
                      >
                        Reset to Default
                      </button>
                    </div>
                    <textarea
                      className="input-field w-full font-mono text-xs"
                      rows={16}
                      value={aiConfig.ai_personalization_prompt}
                      onChange={(e) => setAIConfig({ ...aiConfig, ai_personalization_prompt: e.target.value })}
                      placeholder="Enter your personalization prompt..."
                    />
                  </div>
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <p className="text-xs text-blue-700">
                      AI personalization uses ~300-500 tokens per email. Requires an AI provider with a valid API key configured above.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {canWriteTab('ai') && (
            <div className="flex justify-end">
              <button onClick={() => saveAllSettings('ai')} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save AI Settings'}
              </button>
            </div>
          )}
        </fieldset>
      )}

      {/* Tab 4: Contacts */}
      {activeTab === 'contacts' && (
        <fieldset disabled={!canWriteTab('contacts')} className="space-y-6">
          {!canWriteTab('contacts') && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm">
              You have read-only access to this tab. Contact a super admin to request edit access.
            </div>
          )}
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
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={contactConfig.contact_providers.includes('hunter_contact')} onChange={(e) => { if (e.target.checked) { setContactConfig({ ...contactConfig, contact_providers: [...contactConfig.contact_providers, 'hunter_contact'] }) } else { setContactConfig({ ...contactConfig, contact_providers: contactConfig.contact_providers.filter(s => s !== 'hunter_contact') }) } }} className="w-4 h-4" />
                    <span className="text-sm font-medium">Hunter.io (Contact Finder)</span>
                    {contactConfig.hunter_contact_api_key && <span className="text-xs text-green-600">API key configured</span>}
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={contactConfig.contact_providers.includes('snovio')} onChange={(e) => { if (e.target.checked) { setContactConfig({ ...contactConfig, contact_providers: [...contactConfig.contact_providers, 'snovio'] }) } else { setContactConfig({ ...contactConfig, contact_providers: contactConfig.contact_providers.filter(s => s !== 'snovio') }) } }} className="w-4 h-4" />
                    <span className="text-sm font-medium">Snov.io</span>
                    {contactConfig.snovio_client_id && contactConfig.snovio_client_secret && <span className="text-xs text-green-600">Credentials configured</span>}
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={contactConfig.contact_providers.includes('rocketreach')} onChange={(e) => { if (e.target.checked) { setContactConfig({ ...contactConfig, contact_providers: [...contactConfig.contact_providers, 'rocketreach'] }) } else { setContactConfig({ ...contactConfig, contact_providers: contactConfig.contact_providers.filter(s => s !== 'rocketreach') }) } }} className="w-4 h-4" />
                    <span className="text-sm font-medium">RocketReach</span>
                    {contactConfig.rocketreach_api_key && <span className="text-xs text-green-600">API key configured</span>}
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={contactConfig.contact_providers.includes('pdl')} onChange={(e) => { if (e.target.checked) { setContactConfig({ ...contactConfig, contact_providers: [...contactConfig.contact_providers, 'pdl'] }) } else { setContactConfig({ ...contactConfig, contact_providers: contactConfig.contact_providers.filter(s => s !== 'pdl') }) } }} className="w-4 h-4" />
                    <span className="text-sm font-medium">People Data Labs</span>
                    {contactConfig.pdl_api_key && <span className="text-xs text-green-600">API key configured</span>}
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={contactConfig.contact_providers.includes('proxycurl')} onChange={(e) => { if (e.target.checked) { setContactConfig({ ...contactConfig, contact_providers: [...contactConfig.contact_providers, 'proxycurl'] }) } else { setContactConfig({ ...contactConfig, contact_providers: contactConfig.contact_providers.filter(s => s !== 'proxycurl') }) } }} className="w-4 h-4" />
                    <span className="text-sm font-medium">Proxycurl (LinkedIn)</span>
                    {contactConfig.proxycurl_api_key && <span className="text-xs text-green-600">API key configured</span>}
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

              {contactConfig.contact_providers.includes('hunter_contact') && (
                <div>
                  <label className="label">Hunter.io API Key (Contact Finder)</label>
                  <p className="text-xs text-gray-500 mb-1">Free: 25 req/mo | Paid: from $49/mo — <a href="https://hunter.io/api" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Get API key</a></p>
                  <div className="flex gap-2">
                    <input type="password" value={contactConfig.hunter_contact_api_key} onChange={(e) => setContactConfig({ ...contactConfig, hunter_contact_api_key: e.target.value })} placeholder="Enter Hunter.io API key" className="input flex-1" />
                    <button onClick={() => testConnection('hunter_contact')} disabled={testing === 'hunter_contact' || !contactConfig.hunter_contact_api_key} className="btn-secondary text-sm">
                      {testing === 'hunter_contact' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  {testResults.hunter_contact && (
                    <p className={`text-sm mt-1 ${testResults.hunter_contact.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.hunter_contact.message}
                    </p>
                  )}
                </div>
              )}

              {contactConfig.contact_providers.includes('snovio') && (
                <div>
                  <label className="label">Snov.io Credentials</label>
                  <p className="text-xs text-gray-500 mb-1">Free: 50 credits/mo | Paid: from $39/mo — <a href="https://snov.io/app/api" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Get credentials</a></p>
                  <div className="space-y-2">
                    <div className="flex gap-2">
                      <input type="password" value={contactConfig.snovio_client_id} onChange={(e) => setContactConfig({ ...contactConfig, snovio_client_id: e.target.value })} placeholder="Client ID" className="input flex-1" />
                    </div>
                    <div className="flex gap-2">
                      <input type="password" value={contactConfig.snovio_client_secret} onChange={(e) => setContactConfig({ ...contactConfig, snovio_client_secret: e.target.value })} placeholder="Client Secret" className="input flex-1" />
                      <button onClick={() => testConnection('snovio')} disabled={testing === 'snovio' || !contactConfig.snovio_client_id || !contactConfig.snovio_client_secret} className="btn-secondary text-sm">
                        {testing === 'snovio' ? 'Testing...' : 'Test'}
                      </button>
                    </div>
                  </div>
                  {testResults.snovio && (
                    <p className={`text-sm mt-1 ${testResults.snovio.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.snovio.message}
                    </p>
                  )}
                </div>
              )}

              {contactConfig.contact_providers.includes('rocketreach') && (
                <div>
                  <label className="label">RocketReach API Key</label>
                  <p className="text-xs text-gray-500 mb-1">Free: 5 lookups/mo | Paid: from $99/mo — <a href="https://rocketreach.co/api" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Get API key</a></p>
                  <div className="flex gap-2">
                    <input type="password" value={contactConfig.rocketreach_api_key} onChange={(e) => setContactConfig({ ...contactConfig, rocketreach_api_key: e.target.value })} placeholder="Enter RocketReach API key" className="input flex-1" />
                    <button onClick={() => testConnection('rocketreach')} disabled={testing === 'rocketreach' || !contactConfig.rocketreach_api_key} className="btn-secondary text-sm">
                      {testing === 'rocketreach' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  {testResults.rocketreach && (
                    <p className={`text-sm mt-1 ${testResults.rocketreach.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.rocketreach.message}
                    </p>
                  )}
                </div>
              )}

              {contactConfig.contact_providers.includes('pdl') && (
                <div>
                  <label className="label">People Data Labs API Key</label>
                  <p className="text-xs text-gray-500 mb-1">Free: 100 req/mo | Paid: $0.01/match — <a href="https://www.peopledatalabs.com/signup" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Get API key</a></p>
                  <div className="flex gap-2">
                    <input type="password" value={contactConfig.pdl_api_key} onChange={(e) => setContactConfig({ ...contactConfig, pdl_api_key: e.target.value })} placeholder="Enter PDL API key" className="input flex-1" />
                    <button onClick={() => testConnection('pdl')} disabled={testing === 'pdl' || !contactConfig.pdl_api_key} className="btn-secondary text-sm">
                      {testing === 'pdl' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  {testResults.pdl && (
                    <p className={`text-sm mt-1 ${testResults.pdl.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.pdl.message}
                    </p>
                  )}
                </div>
              )}

              {contactConfig.contact_providers.includes('proxycurl') && (
                <div>
                  <label className="label">Proxycurl API Key</label>
                  <p className="text-xs text-gray-500 mb-1">Free: 10 credits | Paid: $0.01/call — <a href="https://nubela.co/proxycurl" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Get API key</a></p>
                  <div className="flex gap-2">
                    <input type="password" value={contactConfig.proxycurl_api_key} onChange={(e) => setContactConfig({ ...contactConfig, proxycurl_api_key: e.target.value })} placeholder="Enter Proxycurl API key" className="input flex-1" />
                    <button onClick={() => testConnection('proxycurl')} disabled={testing === 'proxycurl' || !contactConfig.proxycurl_api_key} className="btn-secondary text-sm">
                      {testing === 'proxycurl' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  {testResults.proxycurl && (
                    <p className={`text-sm mt-1 ${testResults.proxycurl.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.proxycurl.message}
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Company Enrichment Providers */}
            <div className="mt-6 pt-6 border-t border-gray-200">
              <h4 className="text-md font-semibold text-gray-700 mb-2">Company Enrichment</h4>
              <p className="text-xs text-gray-500 mb-3">Enrich company data with firmographics, tech stack, and corporate records. These providers supplement your lead data.</p>
              <div className="space-y-2 border rounded-lg p-3 bg-gray-50 mb-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={contactConfig.company_enrichment_providers.includes('clearbit')} onChange={(e) => { if (e.target.checked) { setContactConfig({ ...contactConfig, company_enrichment_providers: [...contactConfig.company_enrichment_providers, 'clearbit'] }) } else { setContactConfig({ ...contactConfig, company_enrichment_providers: contactConfig.company_enrichment_providers.filter(s => s !== 'clearbit') }) } }} className="w-4 h-4" />
                  <span className="text-sm font-medium">Clearbit (Breeze)</span>
                  {contactConfig.clearbit_api_key && <span className="text-xs text-green-600">API key configured</span>}
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={contactConfig.company_enrichment_providers.includes('opencorporates')} onChange={(e) => { if (e.target.checked) { setContactConfig({ ...contactConfig, company_enrichment_providers: [...contactConfig.company_enrichment_providers, 'opencorporates'] }) } else { setContactConfig({ ...contactConfig, company_enrichment_providers: contactConfig.company_enrichment_providers.filter(s => s !== 'opencorporates') }) } }} className="w-4 h-4" />
                  <span className="text-sm font-medium">OpenCorporates</span>
                  {contactConfig.opencorporates_api_key && <span className="text-xs text-green-600">API key configured</span>}
                </label>
              </div>

              {contactConfig.company_enrichment_providers.includes('clearbit') && (
                <div className="mb-3">
                  <label className="label">Clearbit API Key</label>
                  <p className="text-xs text-gray-500 mb-1">Free with HubSpot | API: from $99/mo — <a href="https://dashboard.clearbit.com/api" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Get API key</a></p>
                  <div className="flex gap-2">
                    <input type="password" value={contactConfig.clearbit_api_key} onChange={(e) => setContactConfig({ ...contactConfig, clearbit_api_key: e.target.value })} placeholder="Enter Clearbit API key" className="input flex-1" />
                    <button onClick={() => testConnection('clearbit')} disabled={testing === 'clearbit' || !contactConfig.clearbit_api_key} className="btn-secondary text-sm">
                      {testing === 'clearbit' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  {testResults.clearbit && (
                    <p className={`text-sm mt-1 ${testResults.clearbit.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.clearbit.message}
                    </p>
                  )}
                </div>
              )}

              {contactConfig.company_enrichment_providers.includes('opencorporates') && (
                <div className="mb-3">
                  <label className="label">OpenCorporates API Key</label>
                  <p className="text-xs text-gray-500 mb-1">Free: 500 req/mo | Paid: custom pricing — <a href="https://opencorporates.com/api_accounts/new" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Get API key</a></p>
                  <div className="flex gap-2">
                    <input type="password" value={contactConfig.opencorporates_api_key} onChange={(e) => setContactConfig({ ...contactConfig, opencorporates_api_key: e.target.value })} placeholder="Enter OpenCorporates API key" className="input flex-1" />
                    <button onClick={() => testConnection('opencorporates')} disabled={testing === 'opencorporates' || !contactConfig.opencorporates_api_key} className="btn-secondary text-sm">
                      {testing === 'opencorporates' ? 'Testing...' : 'Test'}
                    </button>
                  </div>
                  {testResults.opencorporates && (
                    <p className={`text-sm mt-1 ${testResults.opencorporates.success ? 'text-green-600' : 'text-red-600'}`}>
                      {testResults.opencorporates.message}
                    </p>
                  )}
                </div>
              )}
            </div>

            {contactConfig.contact_providers.length === 1 && contactConfig.contact_providers[0] === 'mock' && contactConfig.company_enrichment_providers.length === 0 && (
              <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-sm text-yellow-700">
                  <strong>Mock Mode:</strong> Using simulated contact data. Enable a provider above for real contact discovery and company enrichment.
                </p>
              </div>
            )}
          </div>

          {canWriteTab('contacts') && (
            <div className="flex justify-end">
              <button onClick={() => saveAllSettings('contacts')} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save Contact Settings'}
              </button>
            </div>
          )}
        </fieldset>
      )}

      {/* Tab 5: Validation */}
      {activeTab === 'validation' && (
        <fieldset disabled={!canWriteTab('validation')} className="space-y-6">
          {!canWriteTab('validation') && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm">
              You have read-only access to this tab. Contact a super admin to request edit access.
            </div>
          )}
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

          {canWriteTab('validation') && (
            <div className="flex justify-end">
              <button onClick={() => saveAllSettings('validation')} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save Validation Settings'}
              </button>
            </div>
          )}
        </fieldset>
      )}

      {/* Tab 6: Outreach */}
      {activeTab === 'outreach' && (
        <fieldset disabled={!canWriteTab('outreach')} className="space-y-6">
          {!canWriteTab('outreach') && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm">
              You have read-only access to this tab. Contact a super admin to request edit access.
            </div>
          )}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-orange-500 rounded-full mr-2"></span>
              Outreach / Email Sending
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Configure how the system sends outreach emails
            </p>

            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
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
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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

          {canWriteTab('outreach') && (
            <div className="flex justify-end">
              <button onClick={() => saveAllSettings('outreach')} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save Outreach Settings'}
              </button>
            </div>
          )}
        </fieldset>
      )}

      {/* Tab 7: Business Rules */}
      {activeTab === 'business' && (
        <fieldset disabled={!canWriteTab('business')} className="space-y-6">
          {!canWriteTab('business') && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm">
              You have read-only access to this tab. Contact a super admin to request edit access.
            </div>
          )}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-1">Company Profile</h3>
            <p className="text-sm text-gray-500 mb-4">Used to auto-populate email signatures when creating mailboxes.</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="label">Company Name</label>
                <input
                  type="text"
                  value={companyProfile.name}
                  onChange={(e) => setCompanyProfile({ ...companyProfile, name: e.target.value })}
                  className="input"
                  placeholder="Your Company Inc."
                />
              </div>
              <div>
                <label className="label">Website</label>
                <input
                  type="text"
                  value={companyProfile.website}
                  onChange={(e) => setCompanyProfile({ ...companyProfile, website: e.target.value })}
                  className="input"
                  placeholder="https://yourcompany.com"
                />
              </div>
              <div>
                <label className="label">Industry</label>
                <input
                  type="text"
                  value={companyProfile.industry}
                  onChange={(e) => setCompanyProfile({ ...companyProfile, industry: e.target.value })}
                  className="input"
                  placeholder="Technology, Healthcare, etc."
                />
              </div>
              <div>
                <label className="label">Company Address</label>
                <input
                  type="text"
                  value={companyProfile.company_address}
                  onChange={(e) => setCompanyProfile({ ...companyProfile, company_address: e.target.value })}
                  className="input"
                  placeholder="123 Business Ave, Suite 100, City, State 12345"
                />
              </div>
            </div>
            {canWriteTab('business') && (
              <div className="flex justify-end mt-4">
                <button onClick={saveCompanyProfile} disabled={savingProfile} className="btn-primary">
                  {savingProfile ? 'Saving...' : 'Save Company Profile'}
                </button>
              </div>
            )}
          </div>

          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">Outreach Limits</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
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
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
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
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
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

          {/* Advanced Delivery & Safety */}
          <div className="border-t border-gray-200 pt-6 mt-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Delivery & Safety</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
              <div>
                <label className="label">Domain Daily Limit (General)</label>
                <input
                  type="number"
                  value={businessRules.domain_daily_limit_default}
                  onChange={(e) => setBusinessRules({ ...businessRules, domain_daily_limit_default: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-gray-500 mt-1">Max emails/day to any single recipient domain</p>
              </div>
              <div>
                <label className="label">Domain Daily Limit (Major Providers)</label>
                <input
                  type="number"
                  value={businessRules.domain_daily_limit_major_providers}
                  onChange={(e) => setBusinessRules({ ...businessRules, domain_daily_limit_major_providers: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-gray-500 mt-1">Gmail, Outlook, Yahoo — stricter limit</p>
              </div>
              <div>
                <label className="label">Max Contacts/Company (All Campaigns)</label>
                <input
                  type="number"
                  value={businessRules.max_contacts_per_company_all_campaigns}
                  onChange={(e) => setBusinessRules({ ...businessRules, max_contacts_per_company_all_campaigns: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-gray-500 mt-1">Cross-campaign cap per company</p>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mt-4">
              <div>
                <label className="label">Send Delay Min (seconds)</label>
                <input
                  type="number"
                  value={businessRules.send_delay_min_sec}
                  onChange={(e) => setBusinessRules({ ...businessRules, send_delay_min_sec: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-gray-500 mt-1">Minimum random delay between outbound emails</p>
              </div>
              <div>
                <label className="label">Send Delay Max (seconds)</label>
                <input
                  type="number"
                  value={businessRules.send_delay_max_sec}
                  onChange={(e) => setBusinessRules({ ...businessRules, send_delay_max_sec: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-gray-500 mt-1">Maximum random delay between outbound emails</p>
              </div>
              <div>
                <label className="label">Data Retention (days)</label>
                <input
                  type="number"
                  value={businessRules.data_retention_days}
                  onChange={(e) => setBusinessRules({ ...businessRules, data_retention_days: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                />
                <p className="text-xs text-gray-500 mt-1">Archived records purged after this many days</p>
              </div>
            </div>
          </div>

          {canWriteTab('business') && (
            <div className="flex justify-end mt-6">
              <button onClick={() => saveAllSettings('business')} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save Business Rules'}
              </button>
            </div>
          )}
        </fieldset>
      )}

      {/* Tab 8: Deliverability */}
      {activeTab === 'deliverability' && (
        <fieldset disabled={!canWriteTab('deliverability')} className="space-y-6">
          {!canWriteTab('deliverability') && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm">
              You have read-only access to this tab. Contact a super admin to request edit access.
            </div>
          )}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-teal-500 rounded-full mr-2"></span>
              Deliverability & Safety
            </h3>
            <p className="text-sm text-gray-500 mb-6">Configure email deliverability thresholds and safety controls</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="label">Complaint Rate Threshold</label>
                <input
                  type="number"
                  value={delivConfig.complaint_rate_threshold}
                  onChange={(e) => setDelivConfig({ ...delivConfig, complaint_rate_threshold: parseFloat(e.target.value) || 0 })}
                  className="input"
                  step="0.001"
                  min="0.001"
                  max="0.01"
                />
                <p className="text-xs text-gray-500 mt-1">Auto-pause mailbox above this rate (0.003 = 0.3%)</p>
              </div>

              <div>
                <label className="label">Domain Daily Limit (General)</label>
                <input
                  type="number"
                  value={delivConfig.domain_daily_limit_default}
                  onChange={(e) => setDelivConfig({ ...delivConfig, domain_daily_limit_default: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                  max="500"
                />
                <p className="text-xs text-gray-500 mt-1">Max emails/day to any single recipient domain</p>
              </div>

              <div>
                <label className="label">Domain Daily Limit (Major Providers)</label>
                <input
                  type="number"
                  value={delivConfig.domain_daily_limit_major_providers}
                  onChange={(e) => setDelivConfig({ ...delivConfig, domain_daily_limit_major_providers: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                  max="200"
                />
                <p className="text-xs text-gray-500 mt-1">Max emails/day to Gmail/Outlook/Yahoo</p>
              </div>

              <div>
                <label className="label">Send Cooldown Days</label>
                <input
                  type="number"
                  value={delivConfig.cooldown_days}
                  onChange={(e) => setDelivConfig({ ...delivConfig, cooldown_days: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                  max="90"
                />
                <p className="text-xs text-gray-500 mt-1">Days between emails to same contact</p>
              </div>

              <div>
                <label className="label">Company Contact Cap</label>
                <input
                  type="number"
                  value={delivConfig.max_contacts_per_company_all_campaigns}
                  onChange={(e) => setDelivConfig({ ...delivConfig, max_contacts_per_company_all_campaigns: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                  max="50"
                />
                <p className="text-xs text-gray-500 mt-1">Max contacts to email at same company</p>
              </div>

              <div>
                <label className="label">Sequence Fatigue Window (Days)</label>
                <input
                  type="number"
                  value={delivConfig.sequence_fatigue_window_days}
                  onChange={(e) => setDelivConfig({ ...delivConfig, sequence_fatigue_window_days: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="7"
                  max="365"
                />
                <p className="text-xs text-gray-500 mt-1">Days to look back for unanswered emails</p>
              </div>

              <div>
                <label className="label">Sequence Fatigue Max Unanswered</label>
                <input
                  type="number"
                  value={delivConfig.sequence_fatigue_max_unanswered}
                  onChange={(e) => setDelivConfig({ ...delivConfig, sequence_fatigue_max_unanswered: parseInt(e.target.value) || 0 })}
                  className="input"
                  min="1"
                  max="20"
                />
                <p className="text-xs text-gray-500 mt-1">Max unanswered emails before auto-stopping</p>
              </div>
            </div>
          </div>

          {canWriteTab('deliverability') && (
            <div className="flex justify-end">
              <button onClick={() => saveAllSettings('deliverability')} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save Deliverability Settings'}
              </button>
            </div>
          )}
        </fieldset>
      )}

      {/* Tab 9: LOB Lead Source API Keys */}
      {activeTab === 'lobleadsources' && (
        <fieldset disabled={!canWriteTab('lobleadsources')} className="space-y-6">
          {!canWriteTab('lobleadsources') && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm">
              You have read-only access to this tab. Contact a super admin to request edit access.
            </div>
          )}
          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center">
              <span className="w-3 h-3 bg-emerald-500 rounded-full mr-2"></span>
              LOB Lead Source API Keys
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              API keys for LOB-specific lead sources (RCM, Software Dev, AI Services, Digital Marketing).
              These are used by non-staffing LOBs to find leads from specialized sources.
            </p>

            <div className="space-y-5">
              {/* Google Places API Key */}
              <div>
                <label className="label">Google Places API Key</label>
                <p className="text-xs text-gray-500 mb-1">
                  Used by: RCM (Google Business), Digital Marketing (Google Business, PageSpeed).
                  Get at <a href="https://console.cloud.google.com" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">console.cloud.google.com</a>
                </p>
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={lobLeadSourceConfig.google_places_api_key}
                    onChange={(e) => setLobLeadSourceConfig({ ...lobLeadSourceConfig, google_places_api_key: e.target.value })}
                    placeholder="Enter Google Places API key"
                    className="input flex-1"
                  />
                  <button
                    onClick={() => testConnection('google_business')}
                    disabled={testing === 'google_business' || !lobLeadSourceConfig.google_places_api_key}
                    className="btn-secondary text-sm"
                  >
                    {testing === 'google_business' ? 'Testing...' : 'Test'}
                  </button>
                </div>
                {testResults['google_business'] && (
                  <p className={`text-xs mt-1 ${testResults['google_business'].success ? 'text-green-600' : 'text-red-600'}`}>
                    {testResults['google_business'].message}
                  </p>
                )}
              </div>

              {/* Crunchbase API Key */}
              <div>
                <label className="label">Crunchbase API Key</label>
                <p className="text-xs text-gray-500 mb-1">
                  Used by: Software Dev, AI Services (company intelligence, funding data).
                  Get at <a href="https://data.crunchbase.com" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">data.crunchbase.com</a>
                </p>
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={lobLeadSourceConfig.crunchbase_api_key}
                    onChange={(e) => setLobLeadSourceConfig({ ...lobLeadSourceConfig, crunchbase_api_key: e.target.value })}
                    placeholder="Enter Crunchbase API key"
                    className="input flex-1"
                  />
                  <button
                    onClick={() => testConnection('crunchbase')}
                    disabled={testing === 'crunchbase' || !lobLeadSourceConfig.crunchbase_api_key}
                    className="btn-secondary text-sm"
                  >
                    {testing === 'crunchbase' ? 'Testing...' : 'Test'}
                  </button>
                </div>
                {testResults['crunchbase'] && (
                  <p className={`text-xs mt-1 ${testResults['crunchbase'].success ? 'text-green-600' : 'text-red-600'}`}>
                    {testResults['crunchbase'].message}
                  </p>
                )}
              </div>

              {/* BuiltWith API Key */}
              <div>
                <label className="label">BuiltWith API Key</label>
                <p className="text-xs text-gray-500 mb-1">
                  Used by: Software Dev, Digital Marketing (technographic data, tech stack analysis).
                  Get at <a href="https://builtwith.com/api" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">builtwith.com/api</a>
                </p>
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={lobLeadSourceConfig.builtwith_api_key}
                    onChange={(e) => setLobLeadSourceConfig({ ...lobLeadSourceConfig, builtwith_api_key: e.target.value })}
                    placeholder="Enter BuiltWith API key"
                    className="input flex-1"
                  />
                  <button
                    onClick={() => testConnection('builtwith')}
                    disabled={testing === 'builtwith' || !lobLeadSourceConfig.builtwith_api_key}
                    className="btn-secondary text-sm"
                  >
                    {testing === 'builtwith' ? 'Testing...' : 'Test'}
                  </button>
                </div>
                {testResults['builtwith'] && (
                  <p className={`text-xs mt-1 ${testResults['builtwith'].success ? 'text-green-600' : 'text-red-600'}`}>
                    {testResults['builtwith'].message}
                  </p>
                )}
              </div>

              {/* GitHub Token */}
              <div>
                <label className="label">GitHub Personal Access Token</label>
                <p className="text-xs text-gray-500 mb-1">
                  Used by: Software Dev, AI Services (GitHub Org adapter). Optional — increases rate limit from 60/hr to 5,000/hr.
                  Get at <a href="https://github.com/settings/tokens" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">github.com/settings/tokens</a>
                </p>
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={lobLeadSourceConfig.github_token}
                    onChange={(e) => setLobLeadSourceConfig({ ...lobLeadSourceConfig, github_token: e.target.value })}
                    placeholder="Enter GitHub token (optional)"
                    className="input flex-1"
                  />
                  <button
                    onClick={() => testConnection('github_org')}
                    disabled={testing === 'github_org'}
                    className="btn-secondary text-sm"
                  >
                    {testing === 'github_org' ? 'Testing...' : 'Test'}
                  </button>
                </div>
                {testResults['github_org'] && (
                  <p className={`text-xs mt-1 ${testResults['github_org'].success ? 'text-green-600' : 'text-red-600'}`}>
                    {testResults['github_org'].message}
                  </p>
                )}
              </div>

              {/* Free adapters info */}
              <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-800">
                <strong>Free adapters (no API key needed):</strong> NPI Registry (healthcare providers), Hiring Signal (internal analysis), News Signal (Google News RSS).
                These are always available for LOBs that use them.
              </div>
            </div>
          </div>

          {canWriteTab('lobleadsources') && (
            <div className="flex justify-end">
              <button onClick={() => saveAllSettings('lobleadsources')} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save LOB Lead Source Settings'}
              </button>
            </div>
          )}
        </fieldset>
      )}

      {/* Tab 10: Source Tuning */}
      {activeTab === 'sourcetuning' && (
        <fieldset disabled={!canWriteTab('sourcetuning')} className="space-y-6">
          {!canWriteTab('sourcetuning') && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-2 rounded-lg text-sm">
              You have read-only access to Source Tuning settings.
            </div>
          )}

          <div className="card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-1">Source Tuning</h3>
            <p className="text-sm text-gray-500 mb-4">Configure adapter performance parameters to control how deeply each job source searches.</p>

            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-6">
              <p className="text-sm text-blue-800">
                Higher values = more leads but more API credits consumed. Recommended values are shown as badges.
                The pipeline uses these when running lead sourcing.
              </p>
            </div>

            {/* Pipeline-level settings */}
            <div className="mb-8">
              <h4 className="text-md font-semibold text-gray-800 mb-3 flex items-center gap-2">
                Pipeline Settings
                <span className="text-xs font-normal bg-gray-100 text-gray-600 px-2 py-0.5 rounded">Global</span>
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Posted Within Days
                    <span className="ml-2 text-xs font-normal bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">Recommended: 7</span>
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={90}
                    value={sourceTuningConfig.posted_within_days}
                    onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, posted_within_days: parseInt(e.target.value) || 7 })}
                    className="input w-full"
                  />
                  <p className="text-xs text-gray-500 mt-1">Only fetch jobs posted within this many days. Lower = fewer duplicates per run. Was hardcoded at 30.</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Adapter Result Limit
                    <span className="ml-2 text-xs font-normal bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">Recommended: 5000</span>
                  </label>
                  <input
                    type="number"
                    min={10}
                    max={50000}
                    value={sourceTuningConfig.pipeline_adapter_limit}
                    onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, pipeline_adapter_limit: parseInt(e.target.value) || 1000 })}
                    className="input w-full"
                  />
                  <p className="text-xs text-gray-500 mt-1">Max results per adapter. High-volume adapters need 5000+.</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Max Workers (Threads)
                    <span className="ml-2 text-xs font-normal bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">Recommended: 10</span>
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={sourceTuningConfig.pipeline_max_workers}
                    onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, pipeline_max_workers: parseInt(e.target.value) || 6 })}
                    className="input w-full"
                  />
                  <p className="text-xs text-gray-500 mt-1">Parallel threads. Set equal to or greater than number of enabled adapters.</p>
                </div>
              </div>
            </div>

            {/* API Cost Optimization — tiered waterfall */}
            <div className="mb-8 border-t pt-6">
              <h4 className="text-md font-semibold text-gray-800 mb-3 flex items-center gap-2">
                API Cost Optimization
                <span className="text-xs font-normal bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded">Tiered Waterfall</span>
              </h4>
              <p className="text-xs text-gray-500 mb-3">
                Free/cheap/unique sources (USAJOBS, Jooble, JSearch, Adzuna, TheirStack) run first.
                Expensive or overlapping sources (Google Jobs, JobDataFeeds, Coresignal) are called
                only to fill the gap toward this many unique leads per run — then skipped to save API spend.
                Providers that share an index (SerpAPI &amp; SearchAPI = Google Jobs) never run together.
              </p>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Unique Leads Target Per Run
                  <span className="ml-2 text-xs font-normal bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">0 = run all sources</span>
                </label>
                <input
                  type="number"
                  min={0}
                  max={100000}
                  value={sourceTuningConfig.lead_sourcing_target_per_run}
                  onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_target_per_run: parseInt(e.target.value) || 0 })}
                  className="input w-full max-w-xs"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Once the cheap tier reaches this many unique leads, expensive Google-Jobs/premium APIs are skipped.
                  Raise it for more coverage; set 0 to disable early-stop (call every enabled source each run).
                </p>
              </div>
            </div>

            {/* Company Exclusion Gate */}
            <div className="mb-8 border-t pt-6">
              <h4 className="text-md font-semibold text-gray-800 mb-3 flex items-center gap-2">
                Company Exclusion Gate
                <span className="text-xs font-normal bg-rose-100 text-rose-700 px-2 py-0.5 rounded">Quality Filter</span>
              </h4>
              <p className="text-xs text-gray-500 mb-4">
                Drops out-of-scope employers at sourcing based on company attributes that keyword
                filters can&apos;t catch by name alone (big brands, IT/staffing/government, confidential
                postings). Missing industry/size is filled by a bounded, cached AI lookup so the gate
                works even for sources that don&apos;t return firmographics. Unknown size/industry is never dropped.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Max Company Size (employees)
                    <span className="ml-2 text-xs font-normal bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">0 = no size limit</span>
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={1000000}
                    value={sourceTuningConfig.lead_sourcing_max_employee_count}
                    onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_max_employee_count: parseInt(e.target.value) || 0 })}
                    className="input w-full"
                  />
                  <p className="text-xs text-gray-500 mt-1">Companies larger than this are dropped (default 500).</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Min Company Size (employees)
                    <span className="ml-2 text-xs font-normal bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">1 = no minimum</span>
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={1000000}
                    value={sourceTuningConfig.lead_sourcing_min_employee_count}
                    onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_min_employee_count: parseInt(e.target.value) || 0 })}
                    className="input w-full"
                  />
                  <p className="text-xs text-gray-500 mt-1">Companies smaller than this are dropped (default 1 = keep all sizes).</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Max AI Enrichment Lookups / Run
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={5000}
                    value={sourceTuningConfig.lead_sourcing_enrich_max_companies}
                    onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_enrich_max_companies: parseInt(e.target.value) || 0 })}
                    className="input w-full"
                    disabled={!sourceTuningConfig.lead_sourcing_enrich_company_at_source}
                  />
                  <p className="text-xs text-gray-500 mt-1">Caps AI company lookups per run for cost/latency (default 300).</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Max Posting Age (days)
                    <span className="ml-2 text-xs font-normal bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">0 = no age limit</span>
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={365}
                    value={sourceTuningConfig.lead_sourcing_max_posting_age_days}
                    onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_max_posting_age_days: parseInt(e.target.value) || 0 })}
                    className="input w-full"
                  />
                  <p className="text-xs text-gray-500 mt-1">Postings older than this are dropped after dedup (default 14). Enforces recency that job-board date filters only hint at.</p>
                </div>
              </div>

              <label className="flex items-center gap-2 cursor-pointer mb-2">
                <input
                  type="checkbox"
                  checked={sourceTuningConfig.lead_sourcing_drop_expired_postings}
                  onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_drop_expired_postings: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-sm font-medium">Drop expired postings (source-provided expiration date in the past)</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer mb-2">
                <input
                  type="checkbox"
                  checked={sourceTuningConfig.lead_sourcing_drop_confidential}
                  onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_drop_confidential: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-sm font-medium">Drop confidential / blank employer postings</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer mb-4">
                <input
                  type="checkbox"
                  checked={sourceTuningConfig.lead_sourcing_enrich_company_at_source}
                  onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_enrich_company_at_source: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-sm font-medium">Fill missing industry/size via AI at sourcing (cached)</span>
              </label>

              {/* High-Applicant Gate (scrape-based, paid) */}
              <div className="mt-4 mb-4 border-t pt-4">
                <label className="flex items-center gap-2 cursor-pointer mb-1">
                  <input
                    type="checkbox"
                    checked={sourceTuningConfig.lead_sourcing_scrape_applicants}
                    onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_scrape_applicants: e.target.checked })}
                    className="w-4 h-4"
                  />
                  <span className="text-sm font-medium">Drop over-competed jobs (scrape LinkedIn/Indeed applicant counts)</span>
                  <span className="ml-1 text-xs font-normal bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">Paid · Firecrawl</span>
                </label>
                <p className="text-xs text-gray-500 mb-3">Requires a Firecrawl API key (<code>FIRECRAWL_API_KEY</code> in .env). Scrapes only linkedin.com/indeed.com URLs, bounded per run. Unknown counts are kept.</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Max Applicants</label>
                    <input
                      type="number"
                      min={0}
                      max={100000}
                      value={sourceTuningConfig.lead_sourcing_max_applicants}
                      onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_max_applicants: parseInt(e.target.value) || 0 })}
                      className="input w-full"
                      disabled={!sourceTuningConfig.lead_sourcing_scrape_applicants}
                    />
                    <p className="text-xs text-gray-500 mt-1">Jobs with more applicants than this are dropped (default 100; 0 = no drop).</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Max Applicant Lookups / Run</label>
                    <input
                      type="number"
                      min={0}
                      max={2000}
                      value={sourceTuningConfig.applicant_scrape_max_lookups}
                      onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, applicant_scrape_max_lookups: parseInt(e.target.value) || 0 })}
                      className="input w-full"
                      disabled={!sourceTuningConfig.lead_sourcing_scrape_applicants}
                    />
                    <p className="text-xs text-gray-500 mt-1">Caps scrapes per run for cost/latency (default 50).</p>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Excluded Industries
                  <span className="ml-2 text-xs font-normal text-gray-400">one per line — empty falls back to defaults</span>
                </label>
                <textarea
                  rows={5}
                  value={sourceTuningConfig.lead_sourcing_excluded_industries.join('\n')}
                  onChange={(e) => setSourceTuningConfig({
                    ...sourceTuningConfig,
                    lead_sourcing_excluded_industries: e.target.value
                      .split(/[\n,]/)
                      .map((s) => s.trim().toLowerCase())
                      .filter(Boolean),
                  })}
                  className="input w-full font-mono text-xs"
                  placeholder={'information technology\nstaffing\ngovernment administration'}
                />
                <div className="flex items-center gap-3 mt-1">
                  <p className="text-xs text-gray-500">
                    Case-insensitive substring match on the company&apos;s industry. Targets like Insurance,
                    Manufacturing, Healthcare are kept.
                  </p>
                  <button
                    type="button"
                    onClick={() => setSourceTuningConfig({ ...sourceTuningConfig, lead_sourcing_excluded_industries: [...DEFAULT_EXCLUDED_INDUSTRIES] })}
                    className="text-xs text-blue-600 hover:underline whitespace-nowrap"
                  >
                    Reset to defaults
                  </button>
                </div>
              </div>
            </div>

            {/* Location Diversification */}
            <div className="mb-8 border-t pt-6">
              <h4 className="text-md font-semibold text-gray-800 mb-3 flex items-center gap-2">
                Location Diversification
                <span className="text-xs font-normal bg-gray-100 text-gray-600 px-2 py-0.5 rounded">Search Strategy</span>
              </h4>
              <label className="flex items-center gap-2 cursor-pointer mb-2">
                <input
                  type="checkbox"
                  checked={sourceTuningConfig.location_diversification}
                  onChange={(e) => setSourceTuningConfig({ ...sourceTuningConfig, location_diversification: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-sm font-medium">Search per state instead of nationwide</span>
              </label>
              <p className="text-xs text-gray-500 ml-6 mb-4">
                Searches each selected state individually instead of &quot;United States&quot;.
                Produces 3-5x more results but uses proportionally more API quota.
                Recommended only with paid API plans.
              </p>

              {sourceTuningConfig.location_diversification && (
                <div className="border rounded-lg bg-gray-50 mt-3">
                  <div className="px-3 py-2 border-b bg-gray-100 rounded-t-lg flex items-center justify-between">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={sourceTuningConfig.target_states.length === US_STATES.length}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSourceTuningConfig({ ...sourceTuningConfig, target_states: [...US_STATES] })
                          } else {
                            setSourceTuningConfig({ ...sourceTuningConfig, target_states: [] })
                          }
                        }}
                        className="w-4 h-4"
                      />
                      <span className="text-sm font-medium">
                        Select All ({sourceTuningConfig.target_states.length}/{US_STATES.length} states)
                      </span>
                    </label>
                  </div>
                  <div className="flex flex-wrap gap-2 p-3">
                    {US_STATES.map((state) => (
                      <label key={state} className="flex items-center gap-1 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={sourceTuningConfig.target_states.includes(state)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSourceTuningConfig({ ...sourceTuningConfig, target_states: [...sourceTuningConfig.target_states, state] })
                            } else {
                              setSourceTuningConfig({ ...sourceTuningConfig, target_states: sourceTuningConfig.target_states.filter(s => s !== state) })
                            }
                          }}
                          className="w-3 h-3"
                        />
                        <span className="text-xs">{state}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Per-adapter tuning cards */}
            <h4 className="text-md font-semibold text-gray-800 mb-3">Per-Adapter Tuning</h4>
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
              {([
                {
                  key: 'jsearch', label: 'JSearch', desc: 'LinkedIn, Indeed, Glassdoor aggregator',
                  fields: [
                    { k: 'batch_size', label: 'Batch Size', def: 4, rec: 8, min: 1, max: 50, impact: 'Titles per query. Higher = fewer API calls.' },
                    { k: 'num_pages', label: 'Num Pages', def: 10, rec: 20, min: 1, max: 100, impact: 'Pages fetched per query. Each page ~ 10 results.' },
                  ],
                },
                {
                  key: 'serpapi', label: 'SerpAPI', desc: 'Google Jobs via SerpAPI',
                  fields: [
                    { k: 'batch_size', label: 'Batch Size', def: 4, rec: 8, min: 1, max: 50, impact: 'Titles per query (OR-joined).' },
                    { k: 'max_pages', label: 'Max Pages', def: 3, rec: 10, min: 1, max: 50, impact: 'Pages per batch. Each page = 1 API credit.' },
                  ],
                },
                {
                  key: 'searchapi', label: 'SearchAPI', desc: 'Google Jobs via SearchAPI.io',
                  fields: [
                    { k: 'batch_size', label: 'Batch Size', def: 4, rec: 8, min: 1, max: 50, impact: 'Titles per query (OR-joined).' },
                    { k: 'max_pages', label: 'Max Pages', def: 3, rec: 10, min: 1, max: 50, impact: 'Pages per batch. Each = 1 API credit.' },
                  ],
                },
                {
                  key: 'adzuna', label: 'Adzuna', desc: 'Adzuna job board API',
                  fields: [
                    { k: 'batch_size', label: 'Batch Size', def: 4, rec: 8, min: 1, max: 50, impact: 'Titles per query.' },
                    { k: 'max_pages', label: 'Max Pages', def: 10, rec: 10, min: 1, max: 50, impact: 'Already optimal at 10.' },
                    { k: 'results_per_page', label: 'Results/Page', def: 50, rec: 50, min: 10, max: 50, impact: 'Max 50 per Adzuna API.' },
                  ],
                },
                {
                  key: 'theirstack', label: 'TheirStack', desc: 'Tech company job postings',
                  fields: [
                    { k: 'batch_size', label: 'Batch Size', def: 20, rec: 20, min: 1, max: 50, impact: 'Already groups 20 titles.' },
                    { k: 'max_pages', label: 'Max Pages', def: 10, rec: 20, min: 1, max: 100, impact: '100 results/page. Double = 2x results.' },
                  ],
                },
                {
                  key: 'usajobs', label: 'USAJobs', desc: 'Federal government jobs (free)',
                  fields: [
                    { k: 'batch_size', label: 'Batch Size', def: 2, rec: 4, min: 1, max: 20, impact: 'Titles per query. Free API, safe to increase.' },
                    { k: 'max_pages', label: 'Max Pages', def: 5, rec: 10, min: 1, max: 50, impact: '100 results/page. Free API.' },
                    { k: 'results_per_page', label: 'Results/Page', def: 100, rec: 100, min: 10, max: 500, impact: 'Results per page from API.' },
                  ],
                },
                {
                  key: 'jooble', label: 'Jooble', desc: '71-country job aggregator (free)',
                  fields: [
                    { k: 'batch_size', label: 'Batch Size', def: 4, rec: 8, min: 1, max: 50, impact: 'Titles per query.' },
                    { k: 'max_pages', label: 'Max Pages', def: 5, rec: 10, min: 1, max: 50, impact: 'Free API, safe to double.' },
                  ],
                },
                {
                  key: 'jobdatafeeds', label: 'JobDataFeeds', desc: 'Bulk job data feed',
                  fields: [
                    { k: 'batch_size', label: 'Batch Size', def: 4, rec: 8, min: 1, max: 50, impact: 'Titles per query.' },
                    { k: 'max_pages', label: 'Max Pages', def: 50, rec: 50, min: 1, max: 200, impact: 'Already excellent (5000/query).' },
                    { k: 'results_per_page', label: 'Results/Page', def: 100, rec: 100, min: 10, max: 500, impact: 'Results per page from API.' },
                  ],
                },
                {
                  key: 'coresignal', label: 'Coresignal', desc: 'Jobs + recruiter contacts (premium)',
                  fields: [
                    { k: 'batch_size', label: 'Batch Size', def: 5, rec: 10, min: 1, max: 50, impact: 'Titles per query.' },
                    { k: 'max_pages', label: 'Max Pages', def: 5, rec: 10, min: 1, max: 50, impact: '2 credits/record — watch cost.' },
                    { k: 'results_per_page', label: 'Results/Page', def: 100, rec: 100, min: 10, max: 500, impact: 'Results per page from API.' },
                  ],
                },
              ] as const).map((adapter) => {
                const isEnabled = jobSourceConfig.lead_sources?.includes(adapter.key)
                return (
                  <div key={adapter.key} className={`border rounded-lg p-4 ${isEnabled ? 'border-green-200 bg-green-50/30' : 'border-gray-200'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <h5 className="text-sm font-semibold text-gray-900">{adapter.label}</h5>
                      {isEnabled ? (
                        <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">Enabled</span>
                      ) : (
                        <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Disabled</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mb-3">{adapter.desc}</p>
                    <div className="space-y-3">
                      {adapter.fields.map((field) => {
                        const currentVal = sourceTuningConfig.job_source_tuning[adapter.key]?.[field.k] ?? field.def
                        return (
                          <div key={field.k}>
                            <div className="flex items-center justify-between mb-1">
                              <label className="text-xs font-medium text-gray-700">{field.label}</label>
                              <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">Rec: {field.rec}</span>
                            </div>
                            <input
                              type="number"
                              min={field.min}
                              max={field.max}
                              value={currentVal}
                              onChange={(e) => {
                                const val = parseInt(e.target.value) || field.def
                                setSourceTuningConfig(prev => ({
                                  ...prev,
                                  job_source_tuning: {
                                    ...prev.job_source_tuning,
                                    [adapter.key]: {
                                      ...prev.job_source_tuning[adapter.key],
                                      [field.k]: val,
                                    },
                                  },
                                }))
                              }}
                              className="input w-full text-sm"
                            />
                            <p className="text-[11px] text-gray-400 mt-0.5">{field.impact}</p>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {canWriteTab('sourcetuning') && (
            <div className="flex justify-end">
              <button
                onClick={() => saveAllSettings('sourcetuning')}
                disabled={saving}
                className="btn btn-primary"
              >
                {saving ? 'Saving...' : 'Save Source Tuning Settings'}
              </button>
            </div>
          )}
        </fieldset>
      )}

      {/* Tab 11: All Settings */}
      {activeTab === 'all' && (
        <div className="card overflow-hidden">
          {!isSuperAdmin && (
            <div className="bg-blue-50 border-b border-blue-200 text-blue-800 px-4 py-2 text-sm">
              Showing settings for tabs you have access to.
            </div>
          )}
          <div className="divide-y divide-gray-200 max-h-96 overflow-y-auto">
            {settings
              .filter((setting) => {
                if (isSuperAdmin) return true
                const tab = SETTING_TAB_MAP[setting.key]
                if (!tab) return true  // unmapped keys are shown
                return tabPermissions[tab] && tabPermissions[tab] !== 'no_access'
              })
              .map((setting) => (
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
          {isSuperAdmin && (
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
          )}
        </div>
      )}

      {/* Pipeline Summary */}
      <div className="mt-8 card p-6 bg-gradient-to-r from-gray-50 to-gray-100">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Complete Pipeline Configuration Summary</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 text-sm">
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

