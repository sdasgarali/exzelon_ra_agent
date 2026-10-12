'use client'

import { useState } from 'react'
import Link from 'next/link'
import { authApi, getApiError } from '@/lib/api'
import { Building, Mail, User, Lock, CheckCircle, Circle } from 'lucide-react'
import BrandLogo from '@/components/brand-logo'

// Mirrors backend/app/schemas/tenant.py SignupRequest.password_strength exactly, so a
// password that passes here is never rejected by the API.
const SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`"

const PASSWORD_RULES: { id: string; label: string; test: (pw: string) => boolean }[] = [
  { id: 'length', label: 'At least 8 characters', test: (pw) => pw.length >= 8 },
  { id: 'upper', label: 'One uppercase letter', test: (pw) => /[A-Z]/.test(pw) },
  { id: 'digit', label: 'One number', test: (pw) => /[0-9]/.test(pw) },
  {
    id: 'special',
    label: 'One special character (!@#$%^&* ...)',
    test: (pw) => Array.from(pw).some((c) => SPECIAL_CHARS.includes(c)),
  },
]

export default function SignupPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [formData, setFormData] = useState({
    full_name: '',
    company_name: '',
    email: '',
    password: '',
  })

  const ruleResults = PASSWORD_RULES.map((r) => ({ ...r, met: r.test(formData.password) }))
  const passwordOk = ruleResults.every((r) => r.met)
  const canSubmit = passwordOk && acceptTerms && !loading

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!passwordOk) {
      setError('Your password does not meet all the requirements listed below the field.')
      return
    }
    if (!acceptTerms) {
      setError('Please accept the Terms of Service and Privacy Policy to continue.')
      return
    }
    setError('')
    setLoading(true)

    try {
      await authApi.signup({ ...formData, accept_terms: true })
      setSuccess(true)
    } catch (err: any) {
      setError(getApiError(err, 'An error occurred. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100 dark:from-gray-900 dark:to-gray-950 px-4">
        <div className="w-full max-w-md">
          <div className="card text-center">
            <div className="w-16 h-16 bg-green-100 dark:bg-green-900/40 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="w-8 h-8 text-green-600 dark:text-green-400" />
            </div>
            <h2 className="text-2xl font-bold text-gray-800 dark:text-gray-100 mb-2">Check your email</h2>
            <p className="text-gray-600 dark:text-gray-300 mb-6">
              We sent a verification link to <strong>{formData.email}</strong>.
              Click the link to activate your account.
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              Didn&apos;t receive the email? Check your spam folder or{' '}
              <button
                onClick={async () => {
                  try {
                    await authApi.resendVerification(formData.email)
                    setError('')
                  } catch {
                    setError('Failed to resend. Please try again later.')
                  }
                }}
                className="text-primary-600 dark:text-primary-400 hover:underline"
              >
                resend it
              </button>.
            </p>
            {error && (
              <div role="alert" className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300 px-4 py-2 rounded-lg text-sm mb-4">{error}</div>
            )}
            <Link href="/login" className="text-primary-600 dark:text-primary-400 hover:text-primary-700 text-sm">
              Back to Sign In
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100 dark:from-gray-900 dark:to-gray-950 px-4 py-8">
      <div className="w-full max-w-md">
        <div className="card">
          <div className="text-center mb-8">
            <div className="flex items-center justify-center mb-4">
              <BrandLogo on="auto" height={40} />
            </div>
            <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">Get Started Free</h1>
            <p className="text-gray-500 dark:text-gray-400 mt-2 text-sm">Create your NeuraLeads account</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="signup-full-name" className="label">Full Name</label>
              <div className="relative">
                <User aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  id="signup-full-name"
                  type="text"
                  autoComplete="name"
                  className="input pl-10"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  placeholder="John Doe"
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="signup-company" className="label">Company Name</label>
              <div className="relative">
                <Building aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  id="signup-company"
                  type="text"
                  autoComplete="organization"
                  className="input pl-10"
                  value={formData.company_name}
                  onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                  placeholder="Acme Inc"
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="signup-email" className="label">Work Email</label>
              <div className="relative">
                <Mail aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  id="signup-email"
                  type="email"
                  autoComplete="email"
                  className="input pl-10"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="you@company.com"
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="signup-password" className="label">Password</label>
              <div className="relative">
                <Lock aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  id="signup-password"
                  type="password"
                  autoComplete="new-password"
                  className="input pl-10"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  placeholder="Create a strong password"
                  aria-describedby="signup-password-rules"
                  aria-invalid={formData.password.length > 0 && !passwordOk}
                  required
                  minLength={8}
                />
              </div>
              <ul
                id="signup-password-rules"
                aria-label="Password requirements"
                className="mt-2 space-y-1 text-xs"
              >
                {ruleResults.map((r) => (
                  <li
                    key={r.id}
                    data-testid={`pw-rule-${r.id}`}
                    data-met={r.met ? 'true' : 'false'}
                    className={`flex items-center gap-1.5 ${
                      r.met ? 'text-green-700 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'
                    }`}
                  >
                    {r.met ? (
                      <CheckCircle aria-hidden="true" className="w-3.5 h-3.5 shrink-0" />
                    ) : (
                      <Circle aria-hidden="true" className="w-3.5 h-3.5 shrink-0" />
                    )}
                    <span>{r.label}</span>
                    <span className="sr-only">{r.met ? '(met)' : '(not met)'}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex items-start gap-2">
              <input
                id="signup-accept-terms"
                type="checkbox"
                checked={acceptTerms}
                onChange={(e) => setAcceptTerms(e.target.checked)}
                required
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500 dark:border-gray-600 dark:bg-gray-700"
              />
              <label htmlFor="signup-accept-terms" className="text-sm text-gray-700 dark:text-gray-300">
                I agree to the{' '}
                <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-primary-600 dark:text-primary-400 underline hover:text-primary-700">
                  Terms of Service
                </a>{' '}
                and{' '}
                <a href="/privacy" target="_blank" rel="noopener noreferrer" className="text-primary-600 dark:text-primary-400 underline hover:text-primary-700">
                  Privacy Policy
                </a>
              </label>
            </div>

            {error && (
              <div role="alert" className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300 px-4 py-2 rounded-lg text-sm">{error}</div>
            )}

            <button
              type="submit"
              className="btn-primary w-full disabled:opacity-60 disabled:cursor-not-allowed"
              disabled={!canSubmit}
            >
              {loading ? 'Creating account...' : 'Create Account'}
            </button>
          </form>

          <div className="mt-6 text-center">
            <Link href="/login" className="text-primary-600 dark:text-primary-400 hover:text-primary-700 text-sm">
              Already have an account? Sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
