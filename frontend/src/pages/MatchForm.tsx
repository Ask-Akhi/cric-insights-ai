import React, { useState } from 'react';

const API_BASE = 'http://127.0.0.1:8001';

export default function MatchForm() {
  const [format, setFormat] = useState('T20');
  const [venue, setVenue] = useState('');
  const [date, setDate] = useState('');
  const [teamA, setTeamA] = useState('');
  const [teamB, setTeamB] = useState('');
  const [squadA, setSquadA] = useState('');
  const [squadB, setSquadB] = useState('');
  const [resp, setResp] = useState<any>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      format,
      venue,
      date,
      team_a: teamA,
      team_b: teamB,
      squad_a: squadA.split(',').map(s => s.trim()).filter(Boolean),
      squad_b: squadB.split(',').map(s => s.trim()).filter(Boolean),
    };
    try {
      const res = await fetch(`${API_BASE}/api/matches`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      setResp(json);
    } catch (err) {
      setResp({ error: String(err) });
    }
  };

  return (
    <div className="p-4 space-y-4">
      <h2 className="text-xl font-semibold">Match Setup</h2>
      <form className="space-y-2" onSubmit={submit}>
        <input className="border p-2 w-full" placeholder="Format (e.g., T20/ODI/Test)" value={format} onChange={e=>setFormat(e.target.value)} />
        <input className="border p-2 w-full" placeholder="Venue" value={venue} onChange={e=>setVenue(e.target.value)} />
        <input className="border p-2 w-full" placeholder="Date (YYYY-MM-DD)" value={date} onChange={e=>setDate(e.target.value)} />
        <input className="border p-2 w-full" placeholder="Team A" value={teamA} onChange={e=>setTeamA(e.target.value)} />
        <input className="border p-2 w-full" placeholder="Team B" value={teamB} onChange={e=>setTeamB(e.target.value)} />
        <textarea className="border p-2 w-full" placeholder="Squad A (comma-separated up to 15)" value={squadA} onChange={e=>setSquadA(e.target.value)} />
        <textarea className="border p-2 w-full" placeholder="Squad B (comma-separated up to 15)" value={squadB} onChange={e=>setSquadB(e.target.value)} />
        <button className="bg-blue-600 text-white px-4 py-2 rounded" type="submit">Submit</button>
      </form>
      {resp && (
        <pre className="bg-gray-100 p-2 text-sm overflow-auto">{JSON.stringify(resp, null, 2)}</pre>
      )}
    </div>
  );
}
