'use client';

import { useState, useEffect } from 'react';
import { authApi } from '@/lib/api';
import { useAuthStore } from '@/lib/store';

/**
 * Self-service account page. Currently exposes the user's own notification
 * preferences (global master toggles for in-app bell + email). Any logged-in
 * user can reach and edit this — unlike the admin Users page.
 */
export default function ProfilePage() {
  const { user, setUser } = useAuthStore();

  const [inApp, setInApp] = useState(true);
  const [email, setEmail] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Hydrate from the freshest server copy (store may predate these fields).
  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then((me) => {
        if (cancelled) return;
        setInApp(me?.notify_inapp_enabled ?? true);
        setEmail(me?.notify_email_enabled ?? true);
        if (me) setUser(me);
      })
      .catch(() => {
        // Fall back to whatever the store has.
        setInApp(user?.notify_inapp_enabled ?? true);
        setEmail(user?.notify_email_enabled ?? true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!success) return;
    const t = setTimeout(() => setSuccess(null), 4000);
    return () => clearTimeout(t);
  }, [success]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await authApi.updateNotificationPreferences({
        notify_inapp_enabled: inApp,
        notify_email_enabled: email,
      });
      if (updated) setUser(updated);
      setSuccess('Notification preferences saved.');
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(detail || (err instanceof Error ? err.message : 'Failed to save preferences.'));
    } finally {
      setSaving(false);
    }
  };

  const Toggle = ({
    checked,
    onChange,
    label,
    description,
  }: {
    checked: boolean;
    onChange: () => void;
    label: string;
    description: string;
  }) => (
    <div className="flex items-start justify-between gap-4 py-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-gray-900 dark:text-white">{label}</p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={`Toggle ${label}`}
        onClick={onChange}
        className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
          checked ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  );

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Profile</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {user?.full_name || user?.email}
        </p>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-800 dark:text-red-200 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-200 px-4 py-3 rounded-lg text-sm">
          {success}
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Notifications</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Choose how you want to be notified — for example, when a deal is assigned to you. Turn both
          off to stop receiving notifications entirely.
        </p>

        {loading ? (
          <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 py-8">
            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Loading…
          </div>
        ) : (
          <div className="mt-4 divide-y divide-gray-200 dark:divide-gray-700">
            <Toggle
              checked={inApp}
              onChange={() => setInApp((v) => !v)}
              label="In-app (bell icon)"
              description="Show notifications in the bell menu at the top of the dashboard."
            />
            <Toggle
              checked={email}
              onChange={() => setEmail((v) => !v)}
              label="Email"
              description="Send notifications to your account email address."
            />
          </div>
        )}

        <div className="mt-6 flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {saving && (
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
            Save changes
          </button>
        </div>
      </div>
    </div>
  );
}
