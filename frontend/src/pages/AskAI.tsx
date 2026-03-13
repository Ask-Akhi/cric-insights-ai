import { useState } from 'react'
import ToolShell from '../components/ToolShell'
import { callAsk } from '../lib/api'

interface Props { apiBase: string; format: string; grounded: boolean }

export default function AskAI({ apiBase, format, grounded }: Props) {
  const [question, setQuestion] = useState('')

  return (
    <ToolShell
      icon="💬"
      title="Ask the Cricket AI"
      subtitle="Free-form cricket questions — stats, fantasy, predictions, tactics"
      onSubmit={() => callAsk(apiBase, {
        prompt: question,
        context: { format },
        grounded,
      })}
    >
      <label className="block text-xs text-slate-400 mb-1 font-medium">Your Question</label>
      <textarea
        className="input h-32 resize-none"
        placeholder="Who should I pick for my fantasy team tonight? What's Rohit Sharma's record in death overs?"
        value={question}
        onChange={e => setQuestion(e.target.value)}
        required
      />
    </ToolShell>
  )
}
