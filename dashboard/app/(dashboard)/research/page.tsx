'use client'

import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, ExternalLink, Play } from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL || 'https://nvc-trader.fly.dev'

const CATEGORIES = [
  { key: 'all',   label: 'All' },
  { key: 'macro', label: 'Macro' },
  { key: 'news',  label: 'News' },
  { key: 'forex', label: 'Forex' },
  { key: 'gold',  label: 'Gold' },
]

interface Video {
  video_id: string
  title: string
  channel: string
  category: string
  published: string
  thumbnail: string
  url: string
  views: number
}

function timeAgo(iso: string): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3_600_000)
  const d = Math.floor(diff / 86_400_000)
  if (d > 30) return `${Math.floor(d / 30)}mo ago`
  if (d > 0)  return `${d}d ago`
  if (h > 0)  return `${h}h ago`
  return 'just now'
}

function fmtViews(n: number): string {
  if (!n) return ''
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M views`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(0)}K views`
  return `${n} views`
}

function VideoCard({ v }: { v: Video }) {
  const [imgOk, setImgOk] = useState(true)
  const catColor: Record<string, string> = {
    macro: 'var(--accent)',
    news:  '#3b82f6',
    forex: 'var(--bull)',
    gold:  '#f59e0b',
  }

  return (
    <a
      href={v.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col rounded border overflow-hidden transition-all hover:border-opacity-60"
      style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--border-bright)')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
    >
      {/* Thumbnail */}
      <div className="relative w-full" style={{ aspectRatio: '16/9', background: 'var(--bg-elevated)' }}>
        {imgOk && v.thumbnail ? (
          <img
            src={v.thumbnail}
            alt={v.title}
            className="w-full h-full object-cover"
            onError={() => setImgOk(false)}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Play size={28} style={{ color: 'var(--text-muted)' }} />
          </div>
        )}
        {/* Play overlay on hover */}
        <div
          className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ background: 'rgba(0,0,0,0.5)' }}
        >
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center"
            style={{ background: 'rgba(255,0,0,0.85)' }}
          >
            <Play size={18} fill="white" color="white" />
          </div>
        </div>
        {/* Category badge */}
        <div
          className="absolute top-2 left-2 px-1.5 py-0.5 rounded text-xs font-mono font-semibold uppercase tracking-wider"
          style={{ background: 'rgba(0,0,0,0.75)', color: catColor[v.category] || 'var(--text-muted)' }}
        >
          {v.category}
        </div>
        {/* Age badge */}
        <div
          className="absolute top-2 right-2 px-1.5 py-0.5 rounded text-xs font-mono"
          style={{ background: 'rgba(0,0,0,0.75)', color: 'var(--text-muted)' }}
        >
          {timeAgo(v.published)}
        </div>
      </div>

      {/* Info */}
      <div className="p-3 flex flex-col gap-1 flex-1">
        <div
          className="text-xs font-mono font-semibold tracking-wider uppercase"
          style={{ color: catColor[v.category] || 'var(--text-muted)' }}
        >
          {v.channel}
        </div>
        <div
          className="text-xs font-semibold leading-snug line-clamp-2"
          style={{ color: 'var(--text-primary)' }}
        >
          {v.title}
        </div>
        {v.views > 0 && (
          <div className="text-xs font-mono mt-auto pt-1" style={{ color: 'var(--text-muted)' }}>
            {fmtViews(v.views)}
          </div>
        )}
      </div>
    </a>
  )
}

function SkeletonCard() {
  return (
    <div className="rounded border overflow-hidden" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
      <div className="skeleton w-full" style={{ aspectRatio: '16/9' }} />
      <div className="p-3 flex flex-col gap-2">
        <div className="skeleton" style={{ width: '40%', height: 10 }} />
        <div className="skeleton" style={{ width: '90%', height: 12 }} />
        <div className="skeleton" style={{ width: '70%', height: 12 }} />
      </div>
    </div>
  )
}

export default function ResearchPage() {
  const [videos,    setVideos]    = useState<Video[]>([])
  const [loading,   setLoading]   = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [category,  setCategory]  = useState('all')
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const load = useCallback(async (cat: string, silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const r = await fetch(`${API}/research/feed?category=${cat}`)
      if (r.ok) {
        const d = await r.json()
        setVideos(d.videos || [])
      }
    } catch {}
    setLoading(false)
    setRefreshing(false)
    setLastRefresh(new Date())
  }, [])

  useEffect(() => { load(category) }, [category])

  const switchCategory = (cat: string) => {
    setCategory(cat)
    load(cat)
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--bg-base)' }}>

      {/* Header */}
      <div className="px-6 py-3 border-b flex items-center justify-between flex-shrink-0"
           style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        <div>
          <h1 className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Research</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Economics Explained · Bloomberg · Patrick Boyle · Kitco · CNBC · Real Vision · ForexSignals
          </p>
        </div>
        <div className="flex items-center gap-2">
          {lastRefresh && (
            <span className="text-xs font-mono hidden sm:block" style={{ color: 'var(--text-muted)' }}>
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => load(category, true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs transition-opacity disabled:opacity-40"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
          >
            <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Category filters */}
      <div className="px-6 py-2 border-b flex items-center gap-2 flex-shrink-0"
           style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        {CATEGORIES.map(c => (
          <button
            key={c.key}
            onClick={() => switchCategory(c.key)}
            className="px-3 py-1 rounded text-xs font-mono font-semibold transition-all"
            style={{
              background: category === c.key ? 'var(--accent)' : 'var(--bg-elevated)',
              color:      category === c.key ? '#000'          : 'var(--text-muted)',
              border:     `1px solid ${category === c.key ? 'var(--accent)' : 'var(--border)'}`,
            }}
          >
            {c.label}
          </button>
        ))}
        {!loading && (
          <span className="ml-auto text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
            {videos.length} videos
          </span>
        )}
      </div>

      {/* Video grid */}
      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {[...Array(12)].map((_, i) => <SkeletonCard key={i} />)}
          </div>
        ) : videos.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 gap-2">
            <ExternalLink size={24} style={{ color: 'var(--text-muted)' }} />
            <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
              No videos fetched — check backend connectivity
            </span>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {videos.map(v => (
              <VideoCard key={v.video_id} v={v} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
