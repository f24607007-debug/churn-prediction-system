import React from 'react';

export default function AdminDashboard() {
  return (
    <div style={{ background: '#f9f9f9', padding: '20px', borderRadius: '8px', border: '1px solid #e1e1e1' }}>
      <h2 style={{ marginTop: '0', fontSize: '20px' }}>Admin Dashboard</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        <div style={{ background: '#fff', padding: '15px', borderRadius: '6px', border: '1px solid #eaeaea' }}>
          <h3 style={{ marginTop: '0', fontSize: '16px' }}>Chatbot Logs Summary</h3>
          <p style={{ fontSize: '24px', fontWeight: 'bold', margin: '10px 0' }}>--</p>
          <span style={{ color: '#666', fontSize: '12px' }}>Total interactions processed</span>
        </div>
        <div style={{ background: '#fff', padding: '15px', borderRadius: '6px', border: '1px solid #eaeaea' }}>
          <h3 style={{ marginTop: '0', fontSize: '16px' }}>Open Escalation Tickets</h3>
          <p style={{ fontSize: '24px', fontWeight: 'bold', margin: '10px 0' }}>--</p>
          <span style={{ color: '#ff4d4f', fontSize: '12px' }}>Awaiting operator review</span>
        </div>
      </div>
    </div>
  );
}
