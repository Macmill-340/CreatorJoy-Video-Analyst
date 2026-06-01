import { useState } from 'react'
import LoginScreen from './components/LoginScreen'
import VideoPanel from './components/VideoPanel'
import ChatPanel from './components/ChatPanel'

export default function App() {
  const [token, setToken] = useState(null)
  const [videos, setVideos] = useState({ a: null, b: null })
  const [messages, setMessages] = useState([])

  if (!token) {
    return <LoginScreen onLogin={setToken} />
  }

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-white">
      <header className="px-6 py-3 bg-gray-900 border-b border-gray-700 flex items-center gap-3">
        <span className="text-2xl">📹</span>
        <h1 className="text-lg font-semibold">CreatorJoy AI Video Analyst</h1>
        <button
          onClick={() => { setToken(null); setVideos({ a: null, b: null }); setMessages([]) }}
          className="ml-auto text-xs text-gray-400 hover:text-white transition"
        >
          Logout
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: Video cards */}
        <div className="w-96 flex-shrink-0 overflow-y-auto border-r border-gray-700 p-4">
          <VideoPanel token={token} onVideosLoaded={setVideos} />
        </div>

        {/* Right: Chat */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <ChatPanel token={token} messages={messages} setMessages={setMessages} />
        </div>
      </div>
    </div>
  )
}
