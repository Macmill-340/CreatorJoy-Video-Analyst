import { useState, useRef, useEffect } from 'react'
import { API } from '../api'

export default function ChatPanel({ token, messages, setMessages }) {
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamBuffer, setStreamBuffer] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamBuffer])

  async function sendMessage() {
    if (!input.trim() || streaming) return
    const userMessage = input.trim()
    setInput('')

    const updatedMessages = [...messages, { role: 'user', content: userMessage }]
    setMessages(updatedMessages)
    setStreaming(true)
    setStreamBuffer('')

    // Build history string from last 4 turns
    const historyText = messages.slice(-4)
      .map(m => `${m.role}: ${m.content}`)
      .join('\n')

    try {
      const res = await fetch(`${API}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: userMessage, history: historyText }),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      // Consume SSE stream token by token
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let fullReply = ''
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE events are separated by blank lines (\n\n). Keep partials in `buffer`.
        const events = buffer.split('\n\n')
        buffer = events.pop() ?? ''

        for (const event of events) {
          for (const line of event.split('\n')) {
            if (!line.startsWith('data: ')) continue
            const payload = line.slice(6).trim()
            if (payload === '[DONE]') continue
            try {
              const parsed = JSON.parse(payload)
              if (parsed.token) {
                fullReply += parsed.token
                setStreamBuffer(fullReply)
              } else if (parsed.error) {
                fullReply += `\n[Error: ${parsed.error}]`
                setStreamBuffer(fullReply)
              }
            } catch {
              // incomplete or malformed JSON — skip silently
            }
          }
        }
      }

      setMessages(prev => [...prev, { role: 'assistant', content: fullReply }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e.message}` }])
    } finally {
      setStreaming(false)
      setStreamBuffer('')
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-gray-700">
        <h2 className="font-semibold text-sm text-gray-300">3. AI Analysis Chat</h2>
        <p className="text-xs text-gray-500">Compare hooks, engagement, transcripts. Responses stream in real time.</p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-gray-500 text-sm mt-8 text-center">
            <p>Try: "Compare the hooks of Video A and Video B"</p>
            <p className="mt-1">Or: "Why did one video get more engagement?"</p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-xl px-4 py-2 rounded-xl text-sm whitespace-pre-wrap ${
                m.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-100'
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}

        {/* Live streaming bubble */}
        {streaming && (
          <div className="flex justify-start">
            <div className="max-w-xl px-4 py-2 rounded-xl text-sm bg-gray-800 text-gray-100 whitespace-pre-wrap">
              {streamBuffer || <span className="animate-pulse text-gray-400">Thinking...</span>}
              <span className="inline-block w-1 h-4 ml-0.5 bg-indigo-400 animate-pulse align-middle" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-700 flex gap-2">
        <textarea
          rows={2}
          className="flex-1 bg-gray-800 rounded-lg px-3 py-2 text-sm text-white outline-none resize-none"
          placeholder="Ask about the videos... (Enter to send, Shift+Enter for newline)"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={streaming}
        />
        <button
          onClick={sendMessage}
          disabled={streaming || !input.trim()}
          className="px-4 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium transition disabled:opacity-50 self-end"
        >
          Send
        </button>
      </div>
    </div>
  )
}