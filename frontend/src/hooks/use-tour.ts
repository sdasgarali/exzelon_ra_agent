'use client'

import { useRef, useCallback, useEffect } from 'react'
import { driver, type Driver } from 'driver.js'
import 'driver.js/dist/driver.css'
import { dashboardTourSteps } from '@/lib/tour-config'

export function useTour() {
  const driverRef = useRef<Driver | null>(null)

  const getDriver = useCallback(() => {
    if (!driverRef.current) {
      driverRef.current = driver({
        showProgress: true,
        animate: true,
        overlayColor: 'rgba(0, 0, 0, 0.6)',
        stagePadding: 8,
        stageRadius: 8,
        popoverClass: 'exzelon-tour-popover',
        steps: dashboardTourSteps,
        nextBtnText: 'Next',
        prevBtnText: 'Back',
        doneBtnText: 'Done',
        onDestroyed: () => {
          localStorage.setItem('tour_completed', 'true')
        },
      })
    }
    return driverRef.current
  }, [])

  const startTour = useCallback(() => {
    const d = getDriver()
    d.drive()
  }, [getDriver])

  const stopTour = useCallback(() => {
    if (driverRef.current) {
      driverRef.current.destroy()
    }
  }, [])

  useEffect(() => {
    return () => {
      if (driverRef.current) {
        driverRef.current.destroy()
        driverRef.current = null
      }
    }
  }, [])

  return { startTour, stopTour }
}
