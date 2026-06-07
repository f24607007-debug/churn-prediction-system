import React, { useState } from 'react';

export default function CustomerChat() {
  const [userId, setUserId] = useState('1');
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    const numericUserId = Number(userId);
    if (!Number.isInteger(numericUserId) || numericUserId <= 0) {
      setMessages(prev => [...prev, { sender: 'bot', text: 'Error: User ID must be a positive integer.' }]);
      return;
    }

    const userMessage = { sender: 'user', text: query };
    setMessages(prev => [...prev, userMessage]);
    setLoading(true);

    try {
      const apiBaseUrl = (import.meta.env?.VITE_API_BASE_URL || '').replace(/\/$/, '');
      const response = await fetch(`${apiBaseUrl}/api/chatbot/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: numericUserId, query: query })
      });
      const contentType = response.headers.get('content-type') || '';
      const payload = contentType.includes('application/json')
        ? await response.json()
        : { status: 'error', message: await response.text() };

      if (response.ok && payload.status === 'success') {
        setMessages(prev => [...prev, { sender: 'bot', text: payload.data.response }]);
      } else {
        setMessages(prev => [...prev, { sender: 'bot', text: `Error: ${payload.message || 'Unexpected response from support service.'}` }]);
      }
    } catch (err) {
      setMessages(prev => [...prev, { sender: 'bot', text: 'Could not connect to support service.' }]);
    } finally {
      setLoading(false);
      setQuery('');
    }
  };

  return (
    <div style={{ background: '#fff', padding: '24px', borderRadius: '24px', border: '1px solid #e5e7eb', boxShadow: '0 20px 60px rgba(15, 23, 42, 0.08)' }}>
      <h2 style={{ marginTop: 0, fontSize: '22px' }}>Customer Support Chat</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '12px', marginBottom: '16px' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '14px', color: '#4b5563' }}>
          User ID
          <input
            type="number"
            min="1"
            value={userId}
            onChange={e => setUserId(e.target.value)}
            style={{ padding: '12px', borderRadius: '12px', border: '1px solid #d1d5db', outline: 'none' }}
          />
        </label>
        <div style={{ color: '#6b7280', fontSize: '14px', alignSelf: 'end' }}>Messages are sent to the chatbot service at <code>/api/chatbot/ask</code>.</div>
      </div>
      <div style={{
        background: '#f8fafc',
        border: '1px solid #e2e8f0',
        borderRadius: '20px',
        padding: '16px',
        height: '320px',
        overflowY: 'auto',
        marginBottom: '16px'
      }}>
        {messages.length === 0 && (
          <p style={{ color: '#64748b', textAlign: 'center', marginTop: '120px' }}>Ask about refunds, shipping, account access, payments, or order status.</p>
        )}
        {messages.map((m, idx) => (
          <div key={idx} style={{
            marginBottom: '10px',
            textAlign: m.sender === 'user' ? 'right' : 'left'
          }}>
            <span style={{
              display: 'inline-block',
              padding: '8px 12px',
              borderRadius: '12px',
              background: m.sender === 'user' ? '#007bff' : '#f1f1f1',
              color: m.sender === 'user' ? '#fff' : '#333',
              maxWidth: '70%',
              wordBreak: 'break-word'
            }}>
              {m.text}
            </span>
          </div>
        ))}
        {loading && <p style={{ color: '#64748b', fontSize: '12px' }}>Bot is thinking...</p>}
      </div>
      <form onSubmit={handleSend} style={{ display: 'flex', gap: '12px' }}>
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Ask a question..."
          style={{
            flex: '1',
            padding: '12px 14px',
            borderRadius: '14px',
            border: '1px solid #d1d5db',
            outline: 'none'
          }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: '12px 22px',
            background: '#111827',
            color: '#fff',
            border: 'none',
            borderRadius: '14px',
            cursor: 'pointer'
          }}
        >
          Send
        </button>
      </form>
    </div>
  );
}
