const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function getSignal() {
  const res = await fetch(`${API_URL}/signal`)
  if (!res.ok) throw new Error('Falha ao buscar sinal')
  return res.json()
}

export async function getMetrics() {
  const res = await fetch(`${API_URL}/metrics`)
  if (!res.ok) throw new Error('Falha ao buscar métricas')
  return res.json()
}

export async function getNews() {
  const res = await fetch(`${API_URL}/news`)
  if (!res.ok) throw new Error('Falha ao buscar notícias')
  return res.json()
}

export async function getRisk() {
  const res = await fetch(`${API_URL}/risk`)
  if (!res.ok) throw new Error('Falha ao buscar status do risk manager')
  return res.json()
}

export async function pauseBot() {
  const res = await fetch(`${API_URL}/risk/pause`, { method: 'POST' })
  if (!res.ok) throw new Error('Falha ao pausar bot')
  return res.json()
}

export async function resumeBot() {
  const res = await fetch(`${API_URL}/risk/resume`, { method: 'POST' })
  if (!res.ok) throw new Error('Falha ao retomar bot')
  return res.json()
}
