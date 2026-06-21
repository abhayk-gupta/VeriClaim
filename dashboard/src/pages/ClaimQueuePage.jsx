import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import useClaimStore from '../store/claimStore';
import api from '../lib/api';
import { RefreshCw } from 'lucide-react';

export default function ClaimQueuePage() {
  const { claims, totalClaims, filters, setClaims, setFilter } = useClaimStore();
  const navigate = useNavigate();

  const fetchClaims = async () => {
    try {
      const params = new URLSearchParams();
      if (filters.status && filters.status !== 'all') {
        params.append('status', filters.status);
      }
      const res = await api.get(`/claims?${params.toString()}`);
      setClaims(res.data.items, res.data.total);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchClaims();
  }, [filters]);

  const tabs = [
    { id: 'escalated', label: 'Escalated' },
    { id: 'pending_clarification', label: 'Pending Clarification' },
    { id: 'all', label: 'All Claims' },
    { id: 'resolved', label: 'Resolved' },
  ];

  return (
    <div style={{ padding: '2rem', height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h2>Claim Queue</h2>
        <button onClick={fetchClaims} className="btn btn-outline">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setFilter('status', tab.id === 'resolved' ? 'approved' : tab.id)}
            className={`btn ${filters.status === tab.id ? 'btn-primary' : 'btn-outline'}`}
            style={{ borderRadius: '99px' }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)' }}>
              <th style={{ padding: '1rem' }}>ID</th>
              <th style={{ padding: '1rem' }}>Type</th>
              <th style={{ padding: '1rem' }}>Status</th>
              <th style={{ padding: '1rem' }}>Age</th>
            </tr>
          </thead>
          <tbody>
            {claims.map(claim => (
              <tr 
                key={claim.id} 
                onClick={() => navigate(`/claims/${claim.id}`)}
                style={{ borderBottom: '1px solid var(--border-color)', cursor: 'pointer' }}
                onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'var(--bg-color)'}
                onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                <td style={{ padding: '1rem', fontFamily: 'monospace' }}>{claim.id.split('-')[0]}</td>
                <td style={{ padding: '1rem' }}>
                  <span className="badge amber">{claim.claim_type}</span>
                </td>
                <td style={{ padding: '1rem' }}>{claim.status}</td>
                <td style={{ padding: '1rem' }}>
                  {Math.round((new Date() - new Date(claim.created_at)) / 60000)}m
                </td>
              </tr>
            ))}
            {claims.length === 0 && (
              <tr>
                <td colSpan={4} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  No claims found matching the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
