import { useState } from 'react'

// Extract YouTube video ID for embed URL
function getYouTubeEmbedUrl(url) {
  const match = url.match(/(?:youtube\.com\/(?:watch\?v=|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/)
  return match ? `https://www.youtube.com/embed/${match[1]}` : null
}

// Instagram blocks iframes with X-Frame-Options: SAMEORIGIN — never embeddable.
// We show a thumbnail card with a click-through link instead.
function InstagramPreviewCard({ url, thumbnailUrl, title, label }) {
  const displayTitle = title || 'Instagram Reel'
  const shortcode = url.match(/instagram\.com\/(?:reels?|p)\/([a-zA-Z0-9_-]+)/)?.[1] || ''

  return (
    <div className="mb-4">
      <p className="text-xs font-semibold text-gray-400 mb-1">Video {label}</p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="block group rounded-lg overflow-hidden border border-gray-700 hover:border-indigo-500 transition"
      >
        {thumbnailUrl ? (
          <div className="relative">
            <img
              src={thumbnailUrl}
              alt={displayTitle}
              className="w-full object-cover max-h-64"
              onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex' }}
            />
            {/* Fallback shown if image fails to load */}
            <div
              className="hidden w-full h-32 bg-gray-800 items-center justify-center"
              style={{ display: 'none' }}
            >
              <span className="text-gray-500 text-xs">Preview unavailable</span>
            </div>
            {/* Play overlay */}
            <div className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 group-hover:opacity-100 transition">
              <div className="bg-white/90 rounded-full w-12 h-12 flex items-center justify-center">
                <svg className="w-5 h-5 text-gray-900 ml-1" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z"/>
                </svg>
              </div>
            </div>
          </div>
        ) : (
          <div className="w-full h-32 bg-gray-800 flex items-center justify-center">
            <span className="text-gray-500 text-xs">No thumbnail</span>
          </div>
        )}
        <div className="bg-gray-800 px-3 py-2 flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-white text-xs font-medium truncate">{displayTitle}</p>
            <p className="text-gray-400 text-xs mt-0.5 truncate">instagram.com/reels/{shortcode}</p>
          </div>
          <svg className="w-4 h-4 text-indigo-400 shrink-0 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </div>
      </a>
    </div>
  )
}

function YouTubeEmbed({ url, label }) {
  const embedUrl = getYouTubeEmbedUrl(url)
  if (!embedUrl) return <p className="text-red-400 text-xs mb-4">Could not embed: {url}</p>
  return (
    <div className="mb-4">
      <p className="text-xs font-semibold text-gray-400 mb-1">Video {label}</p>
      <iframe
        src={embedUrl}
        width="100%"
        height="200"
        frameBorder="0"
        allow="autoplay; clipboard-write; encrypted-media; picture-in-picture"
        allowFullScreen
        className="rounded-lg"
      />
    </div>
  )
}

function VideoPreview({ url, thumbnailUrl, title, label }) {
  if (!url) return null
  const isYT = url.includes('youtube') || url.includes('youtu.be')
  if (isYT) return <YouTubeEmbed url={url} label={label} />
  return <InstagramPreviewCard url={url} thumbnailUrl={thumbnailUrl} title={title} label={label} />
}

export default function VideoPanel({ token, onVideosLoaded }) {
  const [url1, setUrl1] = useState('')
  const [url2, setUrl2] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [analyzed, setAnalyzed] = useState(false)
  const [previews, setPreviews] = useState({ thumbA: '', thumbB: '', titleA: '', titleB: '' })

  async function handleAnalyze() {
    if (!url1 || !url2) return setStatus('Please enter both URLs.')
    setLoading(true)
    setStatus('Extracting metadata and transcripts...')
    try {
      const res = await fetch('/api/analyze_videos', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ url1: url1.trim(), url2: url2.trim() }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Analysis failed')
      }
      const data = await res.json()
      setAnalyzed(true)
      setStatus('✅ Both videos analyzed!')
      setPreviews({
        thumbA: data.thumbnail_a || '',
        thumbB: data.thumbnail_b || '',
        titleA: data.title_a || '',
        titleB: data.title_b || '',
      })
      onVideosLoaded({ a: url1.trim(), b: url2.trim() })
    } catch (e) {
      setStatus(`❌ ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      <h2 className="font-semibold text-sm text-gray-300">1. Ingest Videos</h2>
      <input
        className="w-full bg-gray-800 rounded px-3 py-2 text-white text-xs outline-none"
        placeholder="Video A — YouTube or Instagram URL"
        value={url1}
        onChange={e => setUrl1(e.target.value)}
      />
      <input
        className="w-full bg-gray-800 rounded px-3 py-2 text-white text-xs outline-none"
        placeholder="Video B — YouTube or Instagram URL"
        value={url2}
        onChange={e => setUrl2(e.target.value)}
      />
      <button
        onClick={handleAnalyze}
        disabled={loading}
        className="w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded py-2 text-xs font-medium transition disabled:opacity-50"
      >
        {loading ? 'Analyzing...' : 'Extract & Analyze'}
      </button>
      {status && <p className="text-xs text-gray-400">{status}</p>}

      {analyzed && (
        <>
          <hr className="border-gray-700 my-2" />
          <h2 className="font-semibold text-sm text-gray-300">2. Preview</h2>
          <VideoPreview url={url1} thumbnailUrl={previews.thumbA} title={previews.titleA} label="A" />
          <VideoPreview url={url2} thumbnailUrl={previews.thumbB} title={previews.titleB} label="B" />
        </>
      )}
    </div>
  )
}