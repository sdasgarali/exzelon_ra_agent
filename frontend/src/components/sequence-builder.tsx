'use client'

import { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Mail, Clock, GitBranch, MessageSquare, Phone, Linkedin, Flag, Play } from 'lucide-react'
import type { SequenceStep } from '@/types/api'

// ─── Custom Node Components ─────────────────────────────────────

function StartNode() {
  return (
    <div className="bg-green-500 text-white rounded-full w-12 h-12 flex items-center justify-center shadow-md">
      <Play className="w-5 h-5" />
      <Handle type="source" position={Position.Bottom} className="!bg-green-600" />
    </div>
  )
}

function EndNode() {
  return (
    <div className="bg-gray-400 text-white rounded-full w-12 h-12 flex items-center justify-center shadow-md">
      <Flag className="w-5 h-5" />
      <Handle type="target" position={Position.Top} className="!bg-gray-500" />
    </div>
  )
}

function EmailNode({ data }: { data: any }) {
  const spamColors: Record<string, string> = {
    clean: 'text-green-600',
    low_risk: 'text-yellow-600',
    medium_risk: 'text-orange-600',
    high_risk: 'text-red-600',
    spam: 'text-red-700',
  }
  return (
    <div
      className="bg-white dark:bg-gray-800 border-2 border-blue-400 rounded-lg shadow-md w-56 cursor-pointer hover:shadow-lg transition-shadow"
      onClick={() => data.onEdit?.(data.step)}
    >
      <Handle type="target" position={Position.Top} className="!bg-blue-500" />
      <div className="bg-blue-50 dark:bg-blue-900/20 px-3 py-1.5 rounded-t-md flex items-center gap-2 border-b border-blue-200 dark:border-blue-800">
        <Mail className="w-3.5 h-3.5 text-blue-500" />
        <span className="text-xs font-semibold text-blue-700 dark:text-blue-300">Step {data.stepOrder}</span>
        {data.hasVariants && (
          <span className="ml-auto text-[10px] bg-purple-100 text-purple-700 px-1.5 rounded font-medium">A/B</span>
        )}
      </div>
      <div className="p-3">
        <p className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">{data.subject || '(no subject)'}</p>
        <div className="flex items-center gap-2 mt-1.5 text-[10px] text-gray-500">
          <span>Sent: {data.sent || 0}</span>
          <span>Open: {data.openRate || '0.0'}%</span>
          <span>Reply: {data.replyRate || '0.0'}%</span>
        </div>
        {data.spamGrade && (
          <p className={`text-[10px] mt-1 font-medium ${spamColors[data.spamGrade] || 'text-gray-500'}`}>
            Spam: {data.spamGrade.replace('_', ' ')}
          </p>
        )}
      </div>
      {data.delay > 0 && (
        <div className="px-3 pb-2 text-[10px] text-gray-400">
          Wait {data.delayDays}d {data.delayHours}h before this step
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-blue-500" />
    </div>
  )
}

function WaitNode({ data }: { data: any }) {
  return (
    <div className="bg-yellow-50 dark:bg-yellow-900/20 border-2 border-yellow-400 rounded-lg shadow-md w-40 text-center py-3 cursor-pointer hover:shadow-lg transition-shadow"
      onClick={() => data.onEdit?.(data.step)}>
      <Handle type="target" position={Position.Top} className="!bg-yellow-500" />
      <Clock className="w-5 h-5 text-yellow-500 mx-auto mb-1" />
      <p className="text-xs font-medium text-yellow-700 dark:text-yellow-300">Wait</p>
      <p className="text-sm font-bold text-yellow-800 dark:text-yellow-200">{data.delayDays}d {data.delayHours}h</p>
      <Handle type="source" position={Position.Bottom} className="!bg-yellow-500" />
    </div>
  )
}

function ConditionNode({ data }: { data: any }) {
  return (
    <div
      className="bg-purple-50 dark:bg-purple-900/20 border-2 border-purple-400 rounded-lg shadow-md w-48 text-center py-3 cursor-pointer hover:shadow-lg transition-shadow"
      style={{ transform: 'rotate(0deg)' }}
      onClick={() => data.onEdit?.(data.step)}
    >
      <Handle type="target" position={Position.Top} className="!bg-purple-500" />
      <GitBranch className="w-5 h-5 text-purple-500 mx-auto mb-1" />
      <p className="text-xs font-medium text-purple-700 dark:text-purple-300">Condition</p>
      <p className="text-[11px] text-purple-600 dark:text-purple-400 capitalize">{data.conditionType || 'none'}</p>
      <p className="text-[10px] text-purple-400">{data.windowHours}h window</p>
      <Handle type="source" position={Position.Bottom} id="yes" className="!bg-green-500" style={{ left: '30%' }} />
      <Handle type="source" position={Position.Bottom} id="no" className="!bg-red-500" style={{ left: '70%' }} />
    </div>
  )
}

function SmsNode({ data }: { data: any }) {
  return (
    <div
      className="bg-emerald-50 dark:bg-emerald-900/20 border-2 border-emerald-400 rounded-lg shadow-md w-48 cursor-pointer hover:shadow-lg transition-shadow"
      onClick={() => data.onEdit?.(data.step)}
    >
      <Handle type="target" position={Position.Top} className="!bg-emerald-500" />
      <div className="bg-emerald-100 dark:bg-emerald-900/40 px-3 py-1.5 rounded-t-md flex items-center gap-2 border-b border-emerald-200 dark:border-emerald-800">
        <MessageSquare className="w-3.5 h-3.5 text-emerald-500" />
        <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">SMS Step {data.stepOrder}</span>
      </div>
      <div className="p-3">
        <p className="text-xs text-gray-600 dark:text-gray-400 truncate">{data.bodyPreview || 'No content'}</p>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-emerald-500" />
    </div>
  )
}

function CallNode({ data }: { data: any }) {
  return (
    <div
      className="bg-orange-50 dark:bg-orange-900/20 border-2 border-orange-400 rounded-lg shadow-md w-48 cursor-pointer hover:shadow-lg transition-shadow"
      onClick={() => data.onEdit?.(data.step)}
    >
      <Handle type="target" position={Position.Top} className="!bg-orange-500" />
      <div className="bg-orange-100 dark:bg-orange-900/40 px-3 py-1.5 rounded-t-md flex items-center gap-2 border-b border-orange-200 dark:border-orange-800">
        <Phone className="w-3.5 h-3.5 text-orange-500" />
        <span className="text-xs font-semibold text-orange-700 dark:text-orange-300">Call Step {data.stepOrder}</span>
      </div>
      <div className="p-3">
        <p className="text-xs text-gray-600 dark:text-gray-400">Auto-dial contact</p>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-orange-500" />
    </div>
  )
}

function LinkedinNode({ data }: { data: any }) {
  return (
    <div
      className="bg-sky-50 dark:bg-sky-900/20 border-2 border-sky-400 rounded-lg shadow-md w-48 cursor-pointer hover:shadow-lg transition-shadow opacity-70"
      onClick={() => data.onEdit?.(data.step)}
    >
      <Handle type="target" position={Position.Top} className="!bg-sky-500" />
      <div className="bg-sky-100 dark:bg-sky-900/40 px-3 py-1.5 rounded-t-md flex items-center gap-2 border-b border-sky-200 dark:border-sky-800">
        <Linkedin className="w-3.5 h-3.5 text-sky-600" />
        <span className="text-xs font-semibold text-sky-700 dark:text-sky-300">LinkedIn Step {data.stepOrder}</span>
      </div>
      <div className="p-3">
        <p className="text-xs text-gray-500 italic">Coming soon</p>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-sky-500" />
    </div>
  )
}

const nodeTypes = {
  start: StartNode,
  end: EndNode,
  email: EmailNode,
  wait: WaitNode,
  condition: ConditionNode,
  sms: SmsNode,
  call: CallNode,
  linkedin: LinkedinNode,
}

// ─── Layout Helper ──────────────────────────────────────────────

function buildNodesAndEdges(
  steps: SequenceStep[],
  spamScores: Record<number, { grade: string; score: number }>,
  onEditStep: (step: SequenceStep) => void,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []
  const edges: Edge[] = []

  const X_CENTER = 250
  const Y_START = 0
  const Y_GAP = 130

  // Start node
  nodes.push({
    id: 'start',
    type: 'start',
    position: { x: X_CENTER + 72, y: Y_START },
    data: {},
    draggable: false,
  })

  let y = Y_START + Y_GAP

  steps.forEach((step, i) => {
    const nodeId = `step-${step.step_id}`
    const prevId = i === 0 ? 'start' : `step-${steps[i - 1].step_id}`

    const openRate = step.total_sent > 0 ? ((step.total_opened / step.total_sent) * 100).toFixed(1) : '0.0'
    const replyRate = step.total_sent > 0 ? ((step.total_replied / step.total_sent) * 100).toFixed(1) : '0.0'

    const commonData = {
      step,
      stepOrder: step.step_order,
      delayDays: step.delay_days,
      delayHours: step.delay_hours,
      delay: step.delay_days * 24 + step.delay_hours,
      onEdit: onEditStep,
    }

    let type = step.step_type
    let nodeData: any = commonData

    if (type === 'email') {
      const spam = spamScores[step.step_id]
      nodeData = {
        ...commonData,
        subject: step.subject,
        sent: step.total_sent,
        openRate,
        replyRate,
        hasVariants: !!step.variants_json,
        spamGrade: spam?.grade,
      }
    } else if (type === 'condition') {
      nodeData = {
        ...commonData,
        conditionType: step.condition_type,
        windowHours: step.condition_window_hours,
      }
    } else if (type === 'sms') {
      nodeData = {
        ...commonData,
        bodyPreview: (step.body_text || step.body_html || '').slice(0, 50),
      }
    }

    nodes.push({
      id: nodeId,
      type: type as string,
      position: { x: X_CENTER, y },
      data: nodeData,
    })

    edges.push({
      id: `${prevId}->${nodeId}`,
      source: prevId,
      target: nodeId,
      animated: type === 'condition',
      style: { stroke: '#94a3b8', strokeWidth: 2 },
    })

    y += Y_GAP
  })

  // End node
  const lastId = steps.length > 0 ? `step-${steps[steps.length - 1].step_id}` : 'start'
  nodes.push({
    id: 'end',
    type: 'end',
    position: { x: X_CENTER + 72, y },
    data: {},
    draggable: false,
  })
  edges.push({
    id: `${lastId}->end`,
    source: lastId,
    target: 'end',
    style: { stroke: '#94a3b8', strokeWidth: 2 },
  })

  return { nodes, edges }
}

// ─── Main Component ─────────────────────────────────────────────

interface SequenceBuilderProps {
  steps: SequenceStep[]
  spamScores: Record<number, { grade: string; score: number }>
  onEditStep: (step: SequenceStep) => void
}

export default function SequenceBuilder({ steps, spamScores, onEditStep }: SequenceBuilderProps) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => buildNodesAndEdges(steps, spamScores, onEditStep),
    [steps, spamScores, onEditStep],
  )

  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)

  const canvasHeight = Math.max(400, (steps.length + 2) * 130 + 100)

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden" style={{ height: canvasHeight }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.3}
        maxZoom={1.5}
        nodesDraggable={true}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} size={1} />
        <Controls showInteractive={false} />
        <MiniMap
          nodeStrokeWidth={3}
          className="!bg-gray-50 dark:!bg-gray-900"
          maskColor="rgba(0,0,0,0.1)"
        />
      </ReactFlow>
    </div>
  )
}
