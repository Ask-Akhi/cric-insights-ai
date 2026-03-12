import { useState } from 'react'
import MatchForm from './MatchForm'
import Insights from './Insights'

export default function App() {
  const [data, setData] = useState<any | null>(null)
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Cric Insights</h1>
      <MatchForm onSubmit={setData} />
      {data && <Insights data={data} />}
    </div>
  )
}
