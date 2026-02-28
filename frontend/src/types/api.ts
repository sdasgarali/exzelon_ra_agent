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
