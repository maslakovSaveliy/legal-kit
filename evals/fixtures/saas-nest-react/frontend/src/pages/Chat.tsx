import { useState } from 'react';

export default function Chat() {
  const [text, setText] = useState('');
  const [answer, setAnswer] = useState('');

  async function send() {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/chat`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    setAnswer((await res.json()).answer);
  }

  return (
    <main>
      <h1>Ассистент</h1>
      <textarea value={text} onChange={(e) => setText(e.target.value)} />
      <button onClick={send}>Спросить</button>
      <p>{answer}</p>
    </main>
  );
}
