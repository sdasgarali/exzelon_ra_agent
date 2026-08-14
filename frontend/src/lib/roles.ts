// Central role display helpers. Internal role KEYS are super_admin / admin / bdm /
// recruiter (renamed from operator / viewer) plus any custom, settings-backed keys.
// Labels + colors below cover the built-ins; custom roles fall back to a Title-Cased
// key, or to the label supplied by the roles API when available.

export const BUILTIN_ROLE_LABELS: Record<string, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  bdm: 'BDM',
  recruiter: 'Recruiter',
}

export const ROLE_BADGE_COLORS: Record<string, string> = {
  super_admin: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  admin: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  bdm: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  recruiter: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
}

const DEFAULT_BADGE = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200'

function titleCase(key: string): string {
  return key.split('_').map(w => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w)).join(' ')
}

/** Human label for a role key. Prefers an API-supplied label, then built-ins, then Title Case. */
export function roleLabel(
  key: string | null | undefined,
  roles?: { key: string; label: string }[],
): string {
  if (!key) return ''
  const fromApi = roles?.find(r => r.key === key)?.label
  if (fromApi) return fromApi
  return BUILTIN_ROLE_LABELS[key] || titleCase(key)
}

/** Badge color classes for a role key (built-ins mapped; custom roles get a default). */
export function roleBadgeColor(key: string | null | undefined): string {
  if (!key) return DEFAULT_BADGE
  return ROLE_BADGE_COLORS[key] || DEFAULT_BADGE
}
