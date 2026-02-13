import React, { useState } from 'react'
import { signup, login, recommend } from './api'

export default function App() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [userId, setUserId] = useState(1)
  const [recs, setRecs] = useState([])

  const handleSignup = async () => {
    await signup(username, password)
    alert('signed up')
  }

  const handleLogin = async () => {
    const t = await login(username, password)
    setToken(t)
    alert('logged in')
  }

  const handleRecommend = async () => {
    const r = await recommend(userId, 10, token)
    setRecs(r)
  }

  return (
    <div className="container">
      <h1>Movie Recommender</h1>
      <div className="card">
        <h3>Auth</h3>
        <input placeholder="username" value={username} onChange={e=>setUsername(e.target.value)} />
        <input placeholder="password" type="password" value={password} onChange={e=>setPassword(e.target.value)} />
        <div>
          <button onClick={handleSignup}>Sign Up</button>
          <button onClick={handleLogin}>Log In</button>
        </div>
      </div>

      <div className="card">
        <h3>Recommendations</h3>
        <div style={{display:'flex', gap:8, alignItems:'center'}}>
          <input type="number" value={userId} onChange={e=>setUserId(Number(e.target.value))} style={{width:120}} />
          <button onClick={handleRecommend}>Get Recommendations</button>
        </div>
        <div style={{display:'flex', gap:12, flexWrap:'wrap', marginTop:12}}>
          {recs.map(r => (
            <div key={r.movieId} style={{width:160, border:'1px solid #eee', padding:8, borderRadius:6, background:'#fff'}}>
              <img src={r.poster_url} alt={r.title} style={{width:'100%', height:180, objectFit:'cover'}} />
              <h4 style={{margin:'8px 0 4px'}}>{r.title || `#${r.movieId}`}</h4>
              <div style={{fontSize:12, color:'#666'}}>{r.genres}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
