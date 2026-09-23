// The handbook's section index. Shared by the page (which renders the sections)
// and DocsRail (which renders the contents rail + scroll-spy), so the two can
// never drift apart.
export interface DocSection {
  id: string
  num: string
  title: string
}

export const SECTIONS: DocSection[] = [
  { id: 'overview', num: '01', title: 'What NeuraLeads is' },
  { id: 'concepts', num: '02', title: 'Core concepts' },
  { id: 'workflow', num: '03', title: 'The six-stage workflow' },
  { id: 'setup', num: '04', title: 'Mailboxes & warmup' },
  { id: 'sourcing', num: '05', title: 'Lead sourcing' },
  { id: 'enrichment', num: '06', title: 'Contact enrichment' },
  { id: 'validation', num: '07', title: 'Email validation' },
  { id: 'campaigns', num: '08', title: 'Campaigns & outreach' },
  { id: 'sendgate', num: '09', title: 'The send gate' },
  { id: 'inbox', num: '10', title: 'Inbox, replies & deals' },
  { id: 'ai', num: '11', title: 'What the AI does' },
  { id: 'modules', num: '12', title: 'Screen-by-screen reference' },
  { id: 'integrations', num: '13', title: 'Integrations' },
  { id: 'automation', num: '14', title: 'Background automation' },
  { id: 'roles', num: '15', title: 'Users, roles & permissions' },
  { id: 'plans', num: '16', title: 'Plans, limits & billing' },
  { id: 'data', num: '17', title: 'Your data & privacy' },
  { id: 'rules', num: '18', title: 'Default business rules' },
  { id: 'faq', num: '19', title: 'Frequently asked questions' },
  { id: 'firstweek', num: '21', title: 'Your first week' },
]
