import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../lib/api';

function AuthenticatedImage({ src, alt, style }) {
  const [imgSrc, setImgSrc] = useState(null);

  useEffect(() => {
    if (!src) return;
    api.get(src, { responseType: 'blob' })
      .then(res => {
        const url = URL.createObjectURL(res.data);
        setImgSrc(url);
      })
      .catch(err => console.error("Error loading image", err));
      
    // Cleanup
    return () => {
      if (imgSrc) URL.revokeObjectURL(imgSrc);
    };
  }, [src]);

  if (!imgSrc) return <div style={{ padding: '2rem', backgroundColor: 'var(--bg-color)', textAlign: 'center', borderRadius: '4px' }}>Loading...</div>;

  return <img src={imgSrc} alt={alt} style={style} />;
}

export default function ClaimDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [claim, setClaim] = useState(null);
  const [loading, setLoading] = useState(true);

  const [resolutionNotes, setResolutionNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [clarificationMode, setClarificationMode] = useState(null); // 'whatsapp' | 'voice' | null
  const [whatsappTemplates, setWhatsappTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [customWhatsappMessage, setCustomWhatsappMessage] = useState('');
  const [voiceQuestion, setVoiceQuestion] = useState('');

  const fetchClaim = () => {
    api.get(`/claims/${id}`)
      .then(res => {
        setClaim(res.data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchClaim();
  }, [id]);

  const handleResolve = async (outcome) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await api.post(`/claims/${claim.id}/override`, {
        outcome: outcome,
        resolution_notes: resolutionNotes || 'Resolved manually via dashboard.'
      });
      setResolutionNotes('');
      fetchClaim();
    } catch (e) {
      alert("Error submitting resolution");
    } finally {
      setSubmitting(false);
    }
  };

  const openWhatsapp = () => {
    setClarificationMode('whatsapp');
    api.get('/dashboard/whatsapp-templates').then(res => {
      const templates = res.data.templates || [];
      setWhatsappTemplates(templates);
      if (templates.length > 0) {
        setSelectedTemplate(templates[0].id);
        setCustomWhatsappMessage(templates[0].text);
      }
    }).catch(console.error);
  };

  const handleSendWhatsapp = async () => {
    if (!customWhatsappMessage.trim() || submitting) return;
    
    setSubmitting(true);
    try {
      await api.post(`/dashboard/claims/${claim.id}/send-whatsapp`, {
        message: customWhatsappMessage,
        is_template: selectedTemplate !== '' // Rough estimation if it matches
      });
      alert('WhatsApp message sent!');
      setClarificationMode(null);
      fetchClaim();
    } catch(e) {
      alert('Error sending WhatsApp message');
    } finally {
      setSubmitting(false);
    }
  };

  const handlePlaceCall = async () => {
    if (!voiceQuestion || submitting) return;
    setSubmitting(true);
    try {
      await api.post(`/dashboard/claims/${claim.id}/place-call`, {
        question: voiceQuestion
      });
      alert('Outbound call triggered via background queue!');
      setClarificationMode(null);
      fetchClaim();
    } catch(e) {
      alert('Error placing voice call');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div style={{ padding: '2rem' }}>Loading claim details...</div>;
  if (!claim) return <div style={{ padding: '2rem' }}>Claim not found</div>;

  return (
    <div className="split-pane">
      <div className="left-pane">
        <button onClick={() => navigate('/claims')} className="btn btn-outline" style={{ marginBottom: '1rem' }}>
          &larr; Back to Queue
        </button>
        
        <div className="card">
          <h3>Claim {claim.id.split('-')[0]}</h3>
          <p>Order: {claim.order?.external_order_id}</p>
          <p>Product: {claim.order?.product_description}</p>
          <span className="badge amber">{claim.status}</span>
        </div>

        <div className="card">
          <h3>Evidence</h3>
          <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
            <div style={{ flex: 1 }}>
              <p style={{ fontWeight: 500, marginBottom: '0.5rem' }}>Expected Product</p>
              {claim.order?.product_image_url ? (
                <img src={claim.order.product_image_url} alt="Expected" style={{ width: '100%', borderRadius: '4px' }} />
              ) : (
                <div style={{ padding: '2rem', backgroundColor: 'var(--bg-color)', textAlign: 'center', borderRadius: '4px' }}>
                  No Image Available
                </div>
              )}
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontWeight: 500, marginBottom: '0.5rem' }}>Uploaded Evidence</p>
              {claim.media_r2_key_item ? (
                <AuthenticatedImage src={`/media/${claim.media_r2_key_item}`} alt="Uploaded" style={{ width: '100%', borderRadius: '4px' }} />
              ) : (
                <div style={{ padding: '2rem', backgroundColor: 'var(--bg-color)', textAlign: 'center', borderRadius: '4px' }}>
                  No Uploaded Image
                </div>
              )}
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontWeight: 500, marginBottom: '0.5rem' }}>Shipping Label</p>
              {claim.media_r2_key_label ? (
                <AuthenticatedImage src={`/media/${claim.media_r2_key_label}`} alt="Shipping Label" style={{ width: '100%', borderRadius: '4px' }} />
              ) : (
                <div style={{ padding: '2rem', backgroundColor: 'var(--bg-color)', textAlign: 'center', borderRadius: '4px' }}>
                  No Label Found
                </div>
              )}
            </div>
          </div>
        </div>
        
        <div className="card">
          <h3>Timeline & Interactions</h3>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
            A complete history of AI analyses, customer communications, and system events.
          </p>
          <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {[...claim.interactions || [], ...claim.audit_logs || []]
              .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
              .map(log => {
                const isAudit = !!log.payload; // Audit logs have payloads, Interactions have content_text
                return (
                  <div key={`${isAudit ? 'aud' : 'int'}-${log.id}`} style={{ 
                    padding: '0.75rem', 
                    backgroundColor: 'var(--bg-color)', 
                    borderRadius: '4px',
                    borderLeft: isAudit ? '3px solid var(--warning-color)' : '3px solid var(--primary-color)' 
                  }}>
                    <small style={{ color: 'var(--text-secondary)' }}>{new Date(log.created_at).toLocaleString()}</small>
                    {isAudit ? (
                      <div><strong>AI Pipeline System</strong>: {log.event_type}</div>
                    ) : (
                      <div>
                        <strong>{log.channel}</strong> ({log.direction}): {log.event_type}
                        {log.content_text && <div style={{ marginTop: '0.25rem', padding: '0.5rem', background: 'var(--surface-color)', borderRadius: '4px', fontSize: '0.9rem' }}>{log.content_text}</div>}
                      </div>
                    )}
                  </div>
                )
            })}
          </div>
        </div>
      </div>

      <div className="right-pane">
        <div className="card">
          <h3>AI Analysis</h3>
          <div style={{ marginTop: '1rem' }}>
            <p>Verdict: <span className="badge amber">{claim.policy_verdict || 'N/A'}</span></p>
            <p>Fraud Score: <strong>{claim.fraud_score}</strong></p>
            <p>Reasoning: {claim.agent_reasoning}</p>
          </div>
        </div>

        <div className="card">
          <h3>Resolution Console</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginTop: '1rem' }}>
            <button disabled={submitting || claim.status === 'approved' || claim.status === 'rejected'} onClick={() => handleResolve('refund')} className="btn btn-outline" style={{ color: 'var(--success-color)' }}>Approve (Refund)</button>
            <button disabled={submitting || claim.status === 'approved' || claim.status === 'rejected'} onClick={() => handleResolve('replacement')} className="btn btn-outline" style={{ color: 'var(--success-color)' }}>Approve (Replace)</button>
            <button disabled={submitting || claim.status === 'approved' || claim.status === 'rejected'} onClick={() => handleResolve('rejection')} className="btn btn-outline" style={{ color: 'var(--danger-color)' }}>Reject Claim</button>
            <button disabled={submitting || claim.status === 'approved' || claim.status === 'rejected'} onClick={() => handleResolve('manual_review')} className="btn btn-outline" style={{ color: 'var(--warning-color)' }}>Keep Escalated</button>
          </div>
          <div style={{ marginTop: '1rem' }}>
            <textarea 
              value={resolutionNotes}
              onChange={e => setResolutionNotes(e.target.value)}
              placeholder="Internal resolution notes..." 
              rows={3} 
              style={{ width: '100%', marginBottom: '1rem' }}
              disabled={submitting}
            />
          </div>
        </div>

        <div className="card">
          <h3>Customer Clarification</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginTop: '1rem' }}>
            <button disabled={submitting} onClick={openWhatsapp} className={`btn ${clarificationMode === 'whatsapp' ? 'btn-primary' : 'btn-outline'}`}>Send WhatsApp</button>
            <button disabled={submitting} onClick={() => setClarificationMode('voice')} className={`btn ${clarificationMode === 'voice' ? 'btn-primary' : 'btn-outline'}`}>Initiate Voice Call</button>
          </div>
          
          {clarificationMode === 'whatsapp' && (
            <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: 'var(--bg-color)', borderRadius: '4px' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem' }}>Select Template (Optional)</label>
              <select 
                value={selectedTemplate} 
                onChange={e => {
                  setSelectedTemplate(e.target.value);
                  const t = whatsappTemplates.find(tmpl => tmpl.id === e.target.value);
                  if (t) setCustomWhatsappMessage(t.text);
                }}
                style={{ width: '100%', padding: '0.5rem', marginBottom: '1rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}
              >
                <option value="" disabled>Select a template...</option>
                {whatsappTemplates.map(t => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
              
              <label style={{ display: 'block', marginBottom: '0.5rem' }}>Message Content</label>
              <textarea 
                value={customWhatsappMessage}
                onChange={e => setCustomWhatsappMessage(e.target.value)}
                rows={4}
                style={{ width: '100%', padding: '0.5rem', marginBottom: '1rem', borderRadius: '4px', border: '1px solid var(--border-color)', resize: 'vertical' }}
                placeholder="Type your WhatsApp message here..."
              />
              
              <button disabled={submitting || !customWhatsappMessage.trim()} onClick={handleSendWhatsapp} className="btn btn-primary" style={{ width: '100%' }}>Send Message</button>
            </div>
          )}

          {clarificationMode === 'voice' && (
            <div style={{ marginTop: '1rem', padding: '1rem', backgroundColor: 'var(--bg-color)', borderRadius: '4px' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem' }}>Question for AI Voice Bot to Ask:</label>
              <textarea 
                value={voiceQuestion}
                onChange={e => setVoiceQuestion(e.target.value)}
                placeholder="E.g., Hi, I need to know if the package was fully sealed when you received it?" 
                rows={3} 
                style={{ width: '100%', marginBottom: '1rem' }}
                disabled={submitting}
              />
              <button disabled={submitting || !voiceQuestion} onClick={handlePlaceCall} className="btn btn-primary" style={{ width: '100%' }}>Call Customer Now</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
