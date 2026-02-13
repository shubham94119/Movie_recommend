import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export async function signup(username, password){
  await axios.post(`${API_BASE}/signup`, { username, password })
}

export async function login(username, password){
  const res = await axios.post(`${API_BASE}/login`, { username, password })
  return res.data.access_token
}

export async function recommend(userId, n=10, token){
  const headers = token ? { Authorization: `Bearer ${token}` } : {}
  const res = await axios.get(`${API_BASE}/recommend/${userId}?n=${n}`, { headers })
  return res.data.recommendations
}
