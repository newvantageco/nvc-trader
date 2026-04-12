'use client'

import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type AreaSeriesOptions,
  type HistogramSeriesOptions,
} from 'lightweight-charts'

interface Snapshot {
  timestamp: string
  equity: number
  balance: number
}

interface Props {
  snapshots: Snapshot[]
  height?: number
}

export default function EquityChart({ snapshots, height = 220 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<IChartApi | null>(null)
  const equityRef    = useRef<ISeriesApi<'Area'> | null>(null)
  const ddRef        = useRef<ISeriesApi<'Histogram'> | null>(null)

  useEffect(() => {
    if (!containerRef.current || snapshots.length === 0) return

    // Clean up previous chart
    if (chartRef.current) {
      chartRef.current.remove()
      chartRef.current = null
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background:  { type: ColorType.Solid, color: 'transparent' },
        textColor:   '#475569',
        fontFamily:  "'JetBrains Mono', monospace",
        fontSize:    10,
      },
      grid: {
        vertLines: { color: 'rgba(30,41,59,0.8)', style: LineStyle.Dotted },
        horzLines: { color: 'rgba(30,41,59,0.8)', style: LineStyle.Dotted },
      },
      crosshair: {
        vertLine:  { color: '#f59e0b', labelBackgroundColor: '#f59e0b' },
        horzLine:  { color: '#f59e0b', labelBackgroundColor: '#f59e0b' },
      },
      rightPriceScale: {
        borderColor: '#1e293b',
        textColor:   '#475569',
      },
      timeScale: {
        borderColor:      '#1e293b',
        timeVisible:      true,
        secondsVisible:   false,
        fixLeftEdge:      true,
        fixRightEdge:     true,
      },
      width:  containerRef.current.clientWidth,
      height,
    })
    chartRef.current = chart

    // Equity area series — TradingView green
    const equitySeries = chart.addAreaSeries({
      lineColor:        '#10b981',
      topColor:         'rgba(16,185,129,0.18)',
      bottomColor:      'rgba(16,185,129,0.01)',
      lineWidth:        2,
      priceFormat:      { type: 'price', precision: 2, minMove: 0.01 },
      title:            'Equity',
    } as Partial<AreaSeriesOptions>)
    equityRef.current = equitySeries

    // Drawdown histogram — red below zero
    const ddSeries = chart.addHistogramSeries({
      color:       'rgba(239,68,68,0.35)',
      priceFormat: { type: 'percent', precision: 2, minMove: 0.01 },
      priceScaleId: 'dd',
      title:        'DD%',
    } as Partial<HistogramSeriesOptions>)
    ddRef.current = ddSeries

    chart.priceScale('dd').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
      borderVisible: false,
    })

    // Build series data
    const equityData = snapshots.map(s => ({
      time: Math.floor(new Date(s.timestamp).getTime() / 1000) as unknown as string,
      value: s.equity,
    }))

    // Compute drawdown from running peak
    let peak = -Infinity
    const ddData = snapshots.map(s => {
      if (s.equity > peak) peak = s.equity
      const dd = peak > 0 ? ((s.equity - peak) / peak) * 100 : 0
      return {
        time:  Math.floor(new Date(s.timestamp).getTime() / 1000) as unknown as string,
        value: dd,
        color: dd < -1 ? 'rgba(239,68,68,0.5)' : 'rgba(239,68,68,0.2)',
      }
    })

    equitySeries.setData(equityData)
    ddSeries.setData(ddData)
    chart.timeScale().fitContent()

    // Responsive resize
    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [snapshots, height])

  if (snapshots.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-xs font-mono"
        style={{ height, color: 'var(--text-muted)' }}
      >
        No equity history yet — snapshots write hourly
      </div>
    )
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />
}
