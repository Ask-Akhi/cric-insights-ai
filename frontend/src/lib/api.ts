export interface AskPayload {
  prompt: string
  context?: Record<string, string | number>
  grounded?: boolean
}

export async function callAsk(apiBase: string, payload: AskPayload): Promise<string> {
  const res = await fetch(`${apiBase}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }
  const json = await res.json()
  return json.answer ?? JSON.stringify(json)
}
