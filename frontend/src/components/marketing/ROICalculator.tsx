'use client'

import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import ScrollReveal from './ScrollReveal'

export default function ROICalculator() {
  const [teamSize, setTeamSize] = useState(3)
  const [emailsPerDay, setEmailsPerDay] = useState(500)
  const [currentCost, setCurrentCost] = useState(150)

  const savings = useMemo(() => {
    // Competitor cost estimate: per-seat tools ~ $79/seat/mo average
    const competitorCost = teamSize * 79 + Math.ceil(emailsPerDay / 500) * 20
    // NeuraLeads cost: flat fee, no per-seat
    const exzelonCost = emailsPerDay <= 500 ? 49 : emailsPerDay <= 2500 ? 99 : 199
    const monthlySaving = Math.max(0, (currentCost || competitorCost) - exzelonCost)
    const yearlySaving = monthlySaving * 12
    const pctSaving = currentCost > 0 ? Math.round((monthlySaving / currentCost) * 100) : 0

    return { competitorCost, exzelonCost, monthlySaving, yearlySaving, pctSaving }
  }, [teamSize, emailsPerDay, currentCost])

  return (
    <section className="py-20 px-6">
      <div className="max-w-4xl mx-auto">
        <ScrollReveal>
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              Calculate Your Savings
            </h2>
            <p className="text-slate-400 text-lg">
              See how much you could save by switching to NeuraLeads.
            </p>
          </div>
        </ScrollReveal>

        <ScrollReveal>
          <div className="marketing-card-glow rounded-2xl p-8">
            <div className="grid md:grid-cols-2 gap-10">
              {/* Inputs */}
              <div className="space-y-6">
                <div>
                  <label className="flex justify-between text-sm mb-2">
                    <span className="text-slate-300">Team size</span>
                    <span className="text-white font-semibold">{teamSize} seats</span>
                  </label>
                  <input
                    type="range"
                    min={1}
                    max={20}
                    value={teamSize}
                    onChange={(e) => setTeamSize(+e.target.value)}
                    className="w-full accent-primary-500"
                  />
                </div>

                <div>
                  <label className="flex justify-between text-sm mb-2">
                    <span className="text-slate-300">Emails per day</span>
                    <span className="text-white font-semibold">{emailsPerDay.toLocaleString()}</span>
                  </label>
                  <input
                    type="range"
                    min={100}
                    max={10000}
                    step={100}
                    value={emailsPerDay}
                    onChange={(e) => setEmailsPerDay(+e.target.value)}
                    className="w-full accent-primary-500"
                  />
                </div>

                <div>
                  <label className="flex justify-between text-sm mb-2">
                    <span className="text-slate-300">Current monthly cost</span>
                    <span className="text-white font-semibold">${currentCost}/mo</span>
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={1000}
                    step={10}
                    value={currentCost}
                    onChange={(e) => setCurrentCost(+e.target.value)}
                    className="w-full accent-primary-500"
                  />
                </div>
              </div>

              {/* Results */}
              <div className="flex flex-col justify-center">
                <div className="space-y-4">
                  <div className="flex justify-between items-center py-3 border-b border-white/5">
                    <span className="text-slate-400 text-sm">NeuraLeads cost</span>
                    <span className="text-white font-semibold text-lg">${savings.exzelonCost}/mo</span>
                  </div>
                  <div className="flex justify-between items-center py-3 border-b border-white/5">
                    <span className="text-slate-400 text-sm">Your current cost</span>
                    <span className="text-slate-400 font-semibold text-lg">${currentCost}/mo</span>
                  </div>

                  <motion.div
                    key={savings.monthlySaving}
                    initial={{ scale: 0.95, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="bg-gradient-to-r from-green-500/10 to-emerald-500/10 border border-green-500/20 rounded-xl p-6 text-center"
                  >
                    <div className="text-3xl md:text-4xl font-bold text-green-400">
                      ${savings.yearlySaving.toLocaleString()}/yr
                    </div>
                    <div className="text-green-400/70 text-sm mt-1">
                      {savings.pctSaving > 0 ? `${savings.pctSaving}% savings` : 'estimated savings'} &mdash; ${savings.monthlySaving}/mo
                    </div>
                  </motion.div>
                </div>
              </div>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  )
}
