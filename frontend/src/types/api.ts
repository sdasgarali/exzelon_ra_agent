/** Core API response types to replace `any` across the frontend. */

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Lead {
  lead_id: number;
  client_name: string;
  job_title: string;
  state: string | null;
  posting_date: string | null;
  job_link: string | null;
  salary_min: number | null;
  salary_max: number | null;
  source: string | null;
  lead_status: string;
  first_name: string | null;
  last_name: string | null;
  contact_email: string | null;
  contact_title: string | null;
  skip_reason: string | null;
  ra_name: string | null;
  contact_count: number;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface Contact {
  contact_id: number;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  title: string | null;
  phone: string | null;
  client_name: string | null;
  priority_level: string | null;
  validation_status: string | null;
  source: string | null;
  location_state: string | null;
  timezone: string | null;
  lead_id: number | null;
  lead_ids: number[];
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface Client {
  client_id: number;
  name: string;
  industry: string | null;
  website: string | null;
  employee_count: number | null;
  timezone: string | null;
  lead_count: number;
  contact_count: number;
  is_archived: boolean;
  created_at: string;
}

export interface SenderMailbox {
  mailbox_id: number;
  email: string;
  display_name: string | null;
  warmup_status: string;
  is_active: boolean;
  connection_status: string | null;
  daily_send_limit: number;
  emails_sent_today: number;
  total_emails_sent: number;
  bounce_count: number;
  reply_count: number;
  complaint_count: number;
  health_score: number;
  warmup_days_completed: number;
  created_at: string;
}

export interface EmailTemplate {
  template_id: number;
  name: string;
  subject: string;
  body_html: string;
  body_text: string | null;
  status: string;
  is_default: boolean;
  description: string | null;
  is_archived: boolean;
  created_at: string;
}

export interface JobRun {
  run_id: number;
  pipeline_name: string;
  started_at: string;
  ended_at: string | null;
  status: string;
  counters: string | null;
  records_processed: number;
  records_success: number;
  records_failed: number;
  error_message: string | null;
  triggered_by: string | null;
  duration_seconds: number | null;
}

export interface OutreachEvent {
  event_id: number;
  lead_id: number;
  contact_id: number;
  event_type: string;
  subject: string | null;
  body_html: string | null;
  sent_at: string;
  contact_name: string | null;
  contact_email: string | null;
  sender_email: string | null;
  sender_name: string | null;
}

export interface DashboardKPIs {
  total_leads: number;
  total_contacts: number;
  total_mailboxes: number;
  emails_sent_today: number;
  leads_by_status: Record<string, number>;
  leads_by_source: Record<string, number>;
  contacts_by_validation: Record<string, number>;
}

export interface User {
  user_id: number;
  email: string;
  full_name: string;
  role: "super_admin" | "admin" | "operator" | "viewer";
  is_active: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface AuditLog {
  log_id: number;
  entity_type: string;
  entity_id: number;
  action: string;
  changed_fields: string | null;
  changed_by: string | null;
  notes: string | null;
  created_at: string;
}

// ─── Campaign types ───────────────────────────────────────────────

export interface Campaign {
  campaign_id: number;
  name: string;
  description: string | null;
  status: 'draft' | 'active' | 'paused' | 'completed' | 'archived';
  timezone: string;
  send_window_start: string;
  send_window_end: string;
  send_days: string[];
  mailbox_ids: number[];
  daily_limit: number;
  total_contacts: number;
  total_sent: number;
  total_opened: number;
  total_replied: number;
  total_bounced: number;
  created_by: number | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
  is_archived: boolean;
  enrollment_rules: Record<string, any> | null;
  auto_enrolled_today: number;
  health_score: number | null;
  sending_speed: 'relaxed' | 'normal' | 'aggressive';
  scheduled_send_at: string | null;
  slow_ramp_enabled: boolean;
  slow_ramp_increment: number;
  slow_ramp_current_day: number;
  bounce_threshold: number;
  spam_threshold: number;
  auto_pause_reason: string | null;
  ai_auto_reply_enabled: boolean;
  assignment_mode: string;
  preview_mode: boolean;
  steps?: SequenceStep[];
}

export interface SequenceStep {
  step_id: number;
  campaign_id: number;
  step_order: number;
  step_type: 'email' | 'wait' | 'condition' | 'sms' | 'call' | 'linkedin';
  subject: string | null;
  body_html: string | null;
  body_text: string | null;
  template_id: number | null;
  delay_days: number;
  delay_hours: number;
  reply_to_thread: boolean;
  condition_type: string | null;
  condition_window_hours: number | null;
  yes_next_step: number | null;
  no_next_step: number | null;
  variants_json: string | null;
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  total_replied: number;
  total_bounced: number;
  created_at: string;
}

export interface CampaignContact {
  id: number;
  campaign_id: number;
  contact_id: number;
  lead_id: number | null;
  status: string;
  current_step: number;
  next_send_at: string | null;
  enrolled_at: string | null;
  completed_at: string | null;
  contact_name?: string;
  contact_email?: string;
  contact_company?: string;
  lead_title?: string;
  lead_company?: string;
  lead_state?: string;
}

// ─── Inbox types ──────────────────────────────────────────────────

export interface InboxThread {
  thread_id: string;
  subject: string | null;
  latest_message_at: string | null;
  from_email: string;
  contact_name: string;
  contact_id: number | null;
  mailbox_id: number | null;
  campaign_id: number | null;
  category: string | null;
  sentiment: string | null;
  message_count: number;
  unread_count: number;
  snippet: string;
  direction: string;
}

export interface InboxMessage {
  message_id: number;
  direction: 'sent' | 'received';
  from_email: string;
  to_email: string;
  subject: string | null;
  body_html: string | null;
  body_text: string | null;
  received_at: string | null;
  is_read: boolean;
  category: string | null;
  sentiment: string | null;
  mailbox_id: number | null;
}

export interface InboxThreadDetail {
  thread_id: string;
  contact: {
    contact_id: number;
    name: string;
    email: string;
    title: string | null;
    company: string | null;
    phone: string | null;
  } | null;
  messages: InboxMessage[];
}

// ─── Automation types ─────────────────────────────────────────────

export interface AutomationEvent {
  event_id: number;
  event_type: string;
  source: string;
  title: string;
  details: Record<string, any> | null;
  status: string;
  created_at: string;
}

export interface AutomationSummary {
  period_hours: number;
  total_events: number;
  total_errors: number;
  by_type: Record<string, { total: number; success: number; error: number; skipped: number }>;
  latest_event: { title: string; event_type: string; status: string; created_at: string } | null;
}

// ─── Deal types ───────────────────────────────────────────────────

export interface DealStage {
  stage_id: number;
  name: string;
  stage_order: number;
  color: string;
  is_won: boolean;
  is_lost: boolean;
}

export interface Deal {
  deal_id: number;
  name: string;
  stage_id: number;
  contact_id: number | null;
  client_id: number | null;
  campaign_id: number | null;
  value: number;
  probability: number;
  expected_close_date: string | null;
  owner_id: number | null;
  notes: string | null;
  is_auto_created: boolean;
  probability_manual: boolean;
  won_at: string | null;
  lost_at: string | null;
  lost_reason: string | null;
  created_at: string;
  updated_at: string;
  stage_name?: string;
  stage_color?: string;
  contact_name?: string;
  contact_email?: string;
  client_name?: string;
  activities?: DealActivity[];
}

export interface DealActivity {
  activity_id: number;
  activity_type: string;
  description: string | null;
  metadata_json: string | null;
  created_by: number | null;
  created_at: string | null;
}

export interface DealContactSearch {
  contact_id: number;
  name: string;
  email: string;
  company: string | null;
  title: string | null;
}

export interface DealClientSearch {
  client_id: number;
  name: string;
}

export interface DealForecast {
  weighted_value: number;
  total_pipeline_value: number;
  active_deals: number;
}

export interface StaleDeal {
  deal_id: number;
  name: string;
  stage_id: number;
  value: number;
  days_idle: number;
  last_activity: string;
}

export interface DealPipelineStage extends DealStage {
  deals: Deal[];
  total_value: number;
  count: number;
}

export interface DealStats {
  total_deals: number;
  total_pipeline_value: number;
  won_count: number;
  lost_count: number;
  win_rate: number;
  avg_deal_size: number;
  won_value: number;
}

// ─── Webhook types ────────────────────────────────────────────────

export interface Webhook {
  webhook_id: number;
  name: string;
  url: string;
  events: string[];
  is_active: boolean;
  last_triggered_at: string | null;
  total_deliveries: number;
  total_failures: number;
  created_at: string;
}

// ─── API Key types ────────────────────────────────────────────────

export interface ApiKeyInfo {
  key_id: number;
  name: string;
  key_prefix: string;
  scopes: string[];
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

// ─── Tenant Management types ─────────────────────────────────────

export interface TenantSummary {
  tenant_id: number;
  name: string;
  slug: string;
  plan: string;
  is_active: boolean;
  user_count: number;
  lead_count: number;
  contact_count: number;
  mailbox_count: number;
  campaign_count: number;
  created_at: string | null;
}

export interface TenantUser {
  user_id: number;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  last_login_at: string | null;
}

export interface TenantDetail extends TenantSummary {
  domain: string | null;
  logo_url: string | null;
  max_users: number;
  max_mailboxes: number;
  max_contacts: number;
  max_campaigns: number;
  max_leads: number;
  users: TenantUser[];
}

// ─── Billing & Invoicing ─────────────────────────────────────────────────

export interface Invoice {
  invoice_id: number;
  tenant_id: number;
  invoice_number: string;
  period_start: string | null;
  period_end: string | null;
  due_date: string | null;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  currency: string;
  status: 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled' | 'void';
  paid_at: string | null;
  paid_via: string | null;
  payment_reference: string | null;
  stripe_invoice_id: string | null;
  notes: string | null;
  pdf_path: string | null;
  reminder_count: number;
  last_reminder_at: string | null;
  created_at: string | null;
  is_archived: boolean;
  line_items?: InvoiceLineItem[];
}

export interface InvoiceLineItem {
  line_id: number;
  invoice_id: number;
  description: string;
  quantity: number;
  unit_price_cents: number;
  total_cents: number;
  item_type: 'subscription' | 'addon' | 'credit' | 'tax' | 'discount';
}

export interface PaymentRecord {
  payment_id: number;
  tenant_id: number;
  invoice_id: number | null;
  amount_cents: number;
  currency: string;
  payment_method: string;
  reference: string | null;
  stripe_payment_id: string | null;
  status: 'succeeded' | 'pending' | 'failed' | 'refunded';
  recorded_by: string | null;
  notes: string | null;
  created_at: string | null;
}

export interface BillingStats {
  total_outstanding_cents: number;
  collected_this_month_cents: number;
  overdue_count: number;
  mrr_cents: number;
}

// ─── Deliverability Intelligence ──────────────────────────────────

export interface DeliverabilityHealthSummary {
  avg_health_score: number;
  total_mailboxes: number;
  dns_issues_count: number;
  avg_bounce_rate: number;
  avg_complaint_rate: number;
  bounce_trend: 'up' | 'down' | 'stable';
  send_gate_blocks_today: number;
}

export interface MailboxHealthDetail {
  health_score: number;
  health_grade: string;
  bounce_rate_pct: number;
  reply_rate_pct: number;
  complaint_rate_pct: number;
  engagement_rate: number;
  is_healthy: boolean;
  isp: string;
  isp_name: string;
}

export interface GateCheckResult {
  name: string;
  passed: boolean;
  reason: string;
}

export interface SendGateResult {
  allowed: boolean;
  reason_code: string;
  reason_message: string;
  checks: GateCheckResult[];
}

export interface RenderingWarning {
  severity: 'high' | 'medium' | 'low';
  message: string;
  client: string;
}

export interface RenderingCheckResult {
  warnings: RenderingWarning[];
  stats: Record<string, number>;
  score: number;
}

export interface HumanizeResult {
  subject: string;
  body_html: string;
  body_text: string;
  modifications: string[];
  burstiness_before: number;
  burstiness_after: number;
}

export interface SpintaxPreviewResult {
  variants: string[];
  total_variants: number;
  errors: string[];
}

export interface SpamReduceResult {
  before_score: number;
  before_grade: string;
  after_score: number;
  after_grade: string;
  delta: number;
  new_subject: string;
  new_body_html: string;
}

export interface EngagementScore {
  score: number;
  tier: 'hot' | 'warm' | 'cold' | 'dead';
  signals: Record<string, number>;
  total_sent: number;
  last_engagement_at: string | null;
}

// ─── Campaign Activity Feed ─────────────────────────────────────

export interface CampaignActivityEvent {
  event_id: number;
  contact_email: string;
  contact_name: string;
  event_type: 'sent' | 'opened' | 'clicked' | 'replied' | 'bounced';
  timestamp: string | null;
  step_order: number;
  variant_index: number | null;
  subject: string;
}

// ─── Thread Preview ─────────────────────────────────────────────

export interface ThreadPreviewStep {
  step_order: number;
  step_type: string;
  delay_days: number;
  delay_hours: number;
  subject?: string;
  body_html?: string;
  condition_type?: string;
  condition_window_hours?: number;
}

// ─── Reply Prediction ───────────────────────────────────────────

export interface ReplyPrediction {
  score: number;
  level: 'high' | 'medium' | 'low' | 'unknown';
  factors: Record<string, number>;
}

// ─── Template Library ───────────────────────────────────────────

export interface EmailTemplateExtended extends EmailTemplate {
  industry: string | null;
  goal: string | null;
  is_system: boolean;
}
