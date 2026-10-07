/**
 * Pure helpers for the "API Keys & MCP" settings tab: scope metadata, the
 * hosted MCP URL, and the copy-paste setup snippets for each AI client.
 *
 * Kept free of React so they can be unit-tested in isolation.
 */

import type { ApiKeyScope } from '@/lib/api'

export type { ApiKeyScope }

export const API_KEY_PLACEHOLDER = '<YOUR_API_KEY>'
export const DEFAULT_PUBLIC_ORIGIN = 'https://neuraleads.ai'

export const SCOPE_OPTIONS: { value: ApiKeyScope; label: string; description: string }[] = [
  {
    value: 'read',
    label: 'Read',
    description:
      'Look things up only (leads, contacts, mailboxes, campaigns, warmup, reports). Cannot change anything.',
  },
  {
    value: 'write',
    label: 'Write',
    description:
      'Read, plus operational actions (source leads, enrich, validate, create/launch campaigns, reply to the inbox). Cannot delete, and cannot manage users, billing, roles or API keys.',
  },
  {
    value: 'admin',
    label: 'Admin',
    description: 'Everything the key owner can do, including delete.',
  },
]

export const EXPIRY_OPTIONS: { value: string; label: string; days: number | null }[] = [
  { value: 'never', label: 'Never', days: null },
  { value: '30', label: '30 days', days: 30 },
  { value: '90', label: '90 days', days: 90 },
  { value: '365', label: '1 year (365 days)', days: 365 },
]

/**
 * Derive the public origin of the deployment from an API base URL such as
 * `https://neuraleads.ai/api/v1`. Falls back to the production origin when the
 * value is missing, relative, or unparsable.
 */
export function deriveOrigin(apiUrl: string | undefined | null): string {
  const raw = (apiUrl || '').trim()
  if (!raw) return DEFAULT_PUBLIC_ORIGIN
  try {
    const url = new URL(raw)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return DEFAULT_PUBLIC_ORIGIN
    const path = url.pathname.replace(/\/+$/, '').replace(/\/api\/v1$/, '')
    return `${url.origin}${path}`
  } catch {
    return DEFAULT_PUBLIC_ORIGIN
  }
}

export interface McpEndpoints {
  /** Hosted MCP endpoint, e.g. https://neuraleads.ai/mcp */
  mcpUrl: string
  /** REST API base the stdio server talks to, e.g. https://neuraleads.ai/api/v1 */
  apiUrl: string
}

export function getMcpEndpoints(apiUrl: string | undefined | null): McpEndpoints {
  const origin = deriveOrigin(apiUrl)
  return { mcpUrl: `${origin}/mcp`, apiUrl: `${origin}/api/v1` }
}

export type SnippetId = 'claude_code' | 'claude_desktop' | 'cursor' | 'stdio'

export interface McpSnippet {
  id: SnippetId
  label: string
  /** Where the snippet goes (file path or "Terminal"). */
  location: string
  hint: string
  code: string
}

export function buildMcpSnippets(endpoints: McpEndpoints, apiKey?: string | null): McpSnippet[] {
  const key = apiKey && apiKey.trim() ? apiKey.trim() : API_KEY_PLACEHOLDER
  const { mcpUrl, apiUrl } = endpoints

  const claudeDesktop = {
    mcpServers: {
      neuraleads: {
        command: 'npx',
        args: ['-y', 'mcp-remote', mcpUrl, '--header', `Authorization:Bearer ${key}`],
      },
    },
  }

  const cursor = {
    mcpServers: {
      neuraleads: {
        url: mcpUrl,
        headers: { Authorization: `Bearer ${key}` },
      },
    },
  }

  const stdio = [
    '# 1. Install the connector (from a checkout of this repository)',
    'pip install ./mcp_server',
    '',
    '# 2. Configure it (bash / zsh)',
    `export NEURALEADS_API_URL=${apiUrl}`,
    `export NEURALEADS_API_KEY=${key}`,
    '#    Windows PowerShell:',
    `#    $env:NEURALEADS_API_URL="${apiUrl}"`,
    `#    $env:NEURALEADS_API_KEY="${key}"`,
    '',
    '# 3. Point your MCP client at this command (stdio transport)',
    'neuraleads-mcp',
  ].join('\n')

  return [
    {
      id: 'claude_code',
      label: 'Claude Code',
      location: 'Terminal',
      hint: 'Run once in a terminal. The connector is then available in every Claude Code session.',
      code: `claude mcp add --transport http neuraleads ${mcpUrl} --header "Authorization: Bearer ${key}"`,
    },
    {
      id: 'claude_desktop',
      label: 'Claude Desktop',
      location: 'claude_desktop_config.json',
      hint: 'Settings > Developer > Edit Config, merge this into the file, then restart Claude Desktop. Requires Node.js (for npx).',
      code: JSON.stringify(claudeDesktop, null, 2),
    },
    {
      id: 'cursor',
      label: 'Cursor',
      location: '~/.cursor/mcp.json',
      hint: 'Merge this into ~/.cursor/mcp.json (or .cursor/mcp.json in a project), then reload Cursor.',
      code: JSON.stringify(cursor, null, 2),
    },
    {
      id: 'stdio',
      label: 'Local / self-hosted (stdio)',
      location: 'Terminal',
      hint: 'Run the connector on your own machine and talk to the NeuraLeads API directly.',
      code: stdio,
    },
  ]
}

/** Backend timestamps are naive UTC ISO strings; treat a missing offset as UTC. */
export function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value)
  const d = new Date(hasZone ? value : `${value}Z`)
  return Number.isNaN(d.getTime()) ? null : d
}
