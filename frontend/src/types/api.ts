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
  role: "admin" | "operator" | "viewer";
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
  created_at: string;
  updated_at: string;
  is_archived: boolean;
  enrollment_rules: Record<string, any> | null;
  auto_enrolled_today: number;
  steps?: SequenceStep[];
}

export interface SequenceStep {
  step_id: number;
  campaign_id: number;
  step_order: number;
  step_type: 'email' | 'wait' | 'condition';
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
