import { useState } from 'react'

export default function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleLogin(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username, password }),
      })
      if (!res.ok) throw new Error('Invalid credentials')
      const data = await res.json()
      onLogin(data.access_token)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center justify-center h-screen bg-gray-950">
      <form onSubmit={handleLogin} className="bg-gray-900 p-8 rounded-xl w-80 space-y-4">
        <h2 className="text-xl font-bold text-white">CreatorJoy Login</h2>
        <p className="text-xs text-gray-400">Default: admin / admin123</p>
        <input
          className="w-full bg-gray-800 rounded px-3 py-2 text-white text-sm outline-none"
          placeholder="Username"
          value={username}
          onChange={e => setUsername(e.target.value)}
        />
        <input
          type="password"
          className="w-full bg-gray-800 rounded px-3 py-2 text-white text-sm outline-none"
          placeholder="Password"
          value={password}
          onChange={e => setPassword(e.target.value)}
        />
        {error && <p className="text-red-400 text-xs">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-indigo-600 hover:bg-indigo-500 text-white rounded py-2 text-sm font-medium transition disabled:opacity-50"
        >
          {loading ? 'Logging in...' : 'Login'}
        </button>
      </form>
    </div>
  )
}
