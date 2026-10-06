import { useState } from 'react';
import './App.css';

function App() {
  const [prompt, setPrompt] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState('gemini');

  const handleChat = async () => {
    if (!prompt) return;
    setLoading(true);
    try {
      // Allow overriding API URL for local dev vs Render deployment
      const baseUrl = import.meta.env.VITE_API_URL || '';
      const res = await fetch(`${baseUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, provider })
      });
      const data = await res.json();
      if (res.ok) {
        setResponse(data.response);
      } else {
        setResponse(`Error: ${data.detail}`);
      }
    } catch (err: any) {
      setResponse(`Error: ${err.message}`);
    }
    setLoading(false);
  };

  return (
    <div className="container">
      <header>
        <h1>Temporal Intelligence AI Chat</h1>
        <p>Powered by Gemini & Groq (Llama 3)</p>
      </header>
      
      <main>
        <div className="controls">
          <label htmlFor="provider">Choose AI Provider:</label>
          <select 
            id="provider" 
            value={provider} 
            onChange={(e) => setProvider(e.target.value)}
          >
            <option value="gemini">Google Gemini Pro</option>
            <option value="groq">Groq Llama-3</option>
          </select>
        </div>

        <div className="chat-box">
          <textarea 
            placeholder="Ask anything..." 
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={5}
          />
          <button onClick={handleChat} disabled={loading || !prompt}>
            {loading ? 'Thinking...' : 'Send Message'}
          </button>
        </div>

        {response && (
          <div className="response-box">
            <h3>Response from {provider.toUpperCase()}</h3>
            <div className="response-content">
              {response.split('\n').map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
