import React, { useEffect, useState } from 'react';
import CustomerChat from './pages/CustomerChat';

function getViewFromHash() {
  return window.location.hash === '#dashboard' ? 'dashboard' : 'chat';
}

export default function App() {
  const [activeView, setActiveView] = useState(getViewFromHash);

  useEffect(() => {
    const handleHashChange = () => {
      setActiveView(getViewFromHash());
    };

    window.addEventListener('hashchange', handleHashChange);
    if (!window.location.hash) {
      window.location.hash = '#chat';
    }
    handleHashChange();

    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigateTo = (view) => {
    window.location.hash = view === 'dashboard' ? '#dashboard' : '#chat';
  };

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', minHeight: '100vh', background: 'linear-gradient(180deg, #f7fafc 0%, #ffffff 100%)', color: '#1f2937' }}>
      <div style={{ maxWidth: '1040px', margin: '0 auto', padding: '32px 20px 48px' }}>
        <header style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '28px' }}>
          <div>
            <p style={{ textTransform: 'uppercase', letterSpacing: '0.18em', fontSize: '12px', color: '#6b7280', margin: 0 }}>Churn Prediction System</p>
            <h1 style={{ fontSize: '34px', lineHeight: 1.1, margin: '8px 0 0' }}>Customer support cockpit</h1>
          </div>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button onClick={() => navigateTo('chat')} style={{ padding: '10px 16px', borderRadius: '999px', border: '1px solid #111827', background: activeView === 'chat' ? '#111827' : '#fff', color: activeView === 'chat' ? '#fff' : '#111827', cursor: 'pointer' }}>Customer Chat</button>
            <button onClick={() => navigateTo('dashboard')} style={{ padding: '10px 16px', borderRadius: '999px', border: '1px solid #d1d5db', background: activeView === 'dashboard' ? '#111827' : '#fff', color: activeView === 'dashboard' ? '#fff' : '#111827', cursor: 'pointer' }}>Admin Dashboard</button>
          </div>
        </header>

        {activeView === 'chat' ? (
          <CustomerChat />
        ) : (
          <section style={{ border: '1px solid #e5e7eb', borderRadius: '24px', background: '#fff', padding: '28px' }}>
            <h2 style={{ marginTop: 0 }}>Admin Dashboard</h2>
            <p style={{ marginBottom: 0, color: '#6b7280' }}>Dashboard work is owned elsewhere, so this shell keeps the routing surface visible without coupling to that module.</p>
          </section>
        )}
    </div>
  );
}
