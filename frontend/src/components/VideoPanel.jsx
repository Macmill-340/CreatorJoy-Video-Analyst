import { useState } from 'react'

// Extract YouTube video ID for embed URL
function getYouTubeEmbedUrl(url) {
  const match = url.match(/(?:youtube\.com\/(?:watch\?v=|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/)
  return match ? `https://www.youtube.com/embed/${match[1]}` : null
}

// Extract Instagram reel shortcode for embed URL
function getInstagramEmbedUrl(url) {
  const match = url.match(/instagram\.com\/(?:reel|p)\/([a-zA-Z0-9_-]+)/)
  return match ? `https://www.instagram.com/reel/${match[1]}/embed/` : null
}

function VideoEmbed({ url, label }) {
  if (!url) return null
  const isYT = url.includes('youtube') || url.includes('youtu.be')
  const embedUrl = isYT ? getYouTubeEmbedUrl(url) : getInstagramEmbedUrl(url)
  if (!embedUrl) return <p className="text-red-400 text-xs">Could not embed: {url}</p>

  return (
    <div className="mb-4">
      <p className="text-xs font-semibold text-gray-400 mb-1">Video {label}</p>
      <iframe
        src={embedUrl}
        width="100%"
        height={isYT ? '200' : '560'}
        frameBorder="0"
        allow="autoplay; clipboard-write; encrypted-media; picture-in-picture"
        allowFullScreen
        className="rounded-lg"
      />
    </div>
  )
}

export default function VideoPanel({ token, onVideosLoaded }) {
  const [url1, setUrl1] = useState('')
  const [url2, setUrl2] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [analyzed, setAnalyzed] = useState(false)

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
      setAnalyzed(true)
      setStatus('✅ Both videos analyzed!')
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
          <VideoEmbed url={url1} label="A" />
          <VideoEmbed url={url2} label="B" />
        </>
      )}
    </div>
  )
}
