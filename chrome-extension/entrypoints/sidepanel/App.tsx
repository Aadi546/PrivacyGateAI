import {useEffect, useRef, useState} from 'react';
import {browser} from 'wxt/browser';
import {api, BASE, binaryBlob, inExtension, pair, toBase64} from '../../lib/transport';
import {DEFAULT_REQUIREMENTS, type Binary, type Finding, type Report, type Requirements, type Verification} from '../../lib/types';

type Phase = 'idle' | 'analyzing' | 'awaiting review' | 'redacting' | 'verifying' | 'ready' | 'error';
type Health = {ocr: {available: boolean; error?: string}; processing: string};
const samples = [['aadhaar-scan.png', 'Scanned Aadhaar-like image'], ['aadhaar-text.pdf', 'Text-based Aadhaar-like PDF'], ['pan-scan.png', 'PAN-like image'], ['signature-indicator.pdf', 'Signature-indicator PDF'], ['qr-sample.png', 'Document with a QR code'], ['oversized.png', 'Oversized document (>2 MB)']];
const bytes = (size: number) => size > 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(2)} MB` : `${(size / 1024).toFixed(1)} KB`;

function Icon({name, size = 20}: {name: string; size?: number}) {
  const paths: Record<string, React.ReactNode> = {
    shield: <><path d="m12 3 8 3v6c0 5-4 8-8 10-4-2-8-5-8-10V6Z"/><path d="m8 12 3 3 5-6"/></>,
    upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M8 13h8M8 17h5"/></>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/></>,
    check: <><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/></>,
    download: <><path d="M12 3v13m-5-5 5 5 5-5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/></>,
    activity: <path d="M2 12h5l3-8 4 16 3-8h5"/>,
    sparkle: <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.file}</svg>;
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [token, setToken] = useState('');
  const [pairing, setPairing] = useState(false);
  const [requirements, setRequirements] = useState<Requirements>(DEFAULT_REQUIREMENTS);
  const [phase, setPhase] = useState<Phase>('idle');
  const [report, setReport] = useState<Report | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [preview, setPreview] = useState('');
  const [variant, setVariant] = useState<'original' | 'output'>('original');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [sample, setSample] = useState<string>('aadhaar-scan.png');
  const [dragging, setDragging] = useState(false);
  const sessionRef = useRef<string | null>(null);
  const epoch = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const busy = ['analyzing', 'redacting', 'verifying'].includes(phase);

  useEffect(() => { return () => { if (preview) URL.revokeObjectURL(preview); }; }, [preview]);

  function reset() {
    epoch.current++;
    const old = sessionRef.current;
    sessionRef.current = null;
    if (old) void api({operation: 'delete', session: old}).catch(() => {});
    setReport(null); setPreview(''); setVerification(null); setSelected([]); setConsent(false); setVariant('original'); setPhase('idle'); setError(''); setNotice('');
  }

  useEffect(() => {
    if (!inExtension) return;
    void browser.storage.session.get(['backendToken', 'portalRequirements']).then(async stored => {
      if (stored.portalRequirements) setRequirements(stored.portalRequirements as Requirements);
      if (stored.backendToken) {
        try { setHealth(await api<Health>({operation: 'health'})); } catch { /* Show pairing form after a backend restart. */ }
      }
    });
    const listener = (changes: Record<string, {newValue?: unknown}>, area: string) => {
      if (area === 'session' && changes.portalRequirements?.newValue) {
        reset();
        setRequirements(changes.portalRequirements.newValue as Requirements);
        setNotice('Portal requirements loaded. Inspect a document using these settings.');
      }
    };
    browser.storage.onChanged.addListener(listener);
    return () => browser.storage.onChanged.removeListener(listener);
  }, []);

  async function connect(event: React.FormEvent) {
    event.preventDefault();
    setPairing(true); setError('');
    try { setHealth(await pair(token.trim()) as Health); setToken(''); setNotice('Paired with the local backend. Your documents stay on this computer.'); }
    catch (problem) { setError(problem instanceof Error ? problem.message : 'Pairing failed.'); }
    finally { setPairing(false); }
  }

  async function showPreview(session: string, output: boolean, version = epoch.current) {
    const binary = await api<Binary>({operation: 'preview', session, variant: output ? 'output' : 'original'});
    if (version !== epoch.current || session !== sessionRef.current) return;
    setPreview(URL.createObjectURL(binaryBlob(binary)));
    setVariant(output ? 'output' : 'original');
  }

  async function inspect(file: File) {
    if (busy || !health) return;
    if (!file.size || file.size > 10 * 1024 * 1024) { setError('Choose a non-empty PDF, PNG, or JPEG smaller than 10 MB.'); return; }
    reset();
    const version = epoch.current;
    setPhase('analyzing');
    try {
      const fileBytes = toBase64(await file.arrayBuffer());
      const result = await api<Report>({operation: 'analyze', file: fileBytes, filename: file.name, requirements});
      if (version !== epoch.current) { void api({operation: 'delete', session: result.session_id}); return; }
      sessionRef.current = result.session_id;
      setReport(result);
      await showPreview(result.session_id, false, version);
      if (version === epoch.current) setPhase('awaiting review');
    } catch (problem) {
      if (version === epoch.current) { setError(problem instanceof Error ? problem.message : 'Inspection failed.'); setPhase('error'); }
    }
  }

  async function useSample() {
    if (busy || !health) return;
    setError('');
    try {
      const binary = await api<Binary>({operation: 'sample', sample});
      await inspect(new File([binaryBlob(binary)], sample, {type: binary.mime}));
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Sample could not load.'); }
  }

  function toggleFinding(finding: Finding) {
    setSelected(values => values.includes(finding.id) ? values.filter(id => id !== finding.id) : [...values, finding.id]);
    setConsent(false); setVerification(null); setNotice('');
    if (report && variant === 'output') { setPreview(''); void showPreview(report.session_id, false).catch(problem => setError(problem.message)); }
    setPhase('awaiting review');
  }

  async function protect() {
    if (!report || !selected.length || !consent || busy) return;
    const version = epoch.current;
    setPhase('redacting'); setError(''); setVerification(null); setNotice('');
    try {
      const result = await api<{verification: Verification}>({operation: 'redact', session: report.session_id, finding_ids: selected});
      if (version !== epoch.current) return;
      setPhase('verifying');
      setVerification(result.verification);
      await showPreview(report.session_id, true, version);
      if (version !== epoch.current) return;
      setPhase(result.verification.status === 'passed_supported_checks' ? 'ready' : 'error');
      if (result.verification.status !== 'passed_supported_checks') setError('Required output checks did not pass. Download is blocked; review the verification report.');
    } catch (problem) {
      if (version === epoch.current) { setError(problem instanceof Error ? problem.message : 'Redaction failed.'); setPhase('error'); }
    }
  }

  async function download() {
    if (!report || verification?.status !== 'passed_supported_checks' || !verification.checks.length || !verification.checks.every(check => check.removed && check.replacement_rendered) || busy) return;
    try {
      const binary = await api<Binary>({operation: 'download', session: report.session_id});
      const url = URL.createObjectURL(binaryBlob(binary));
      const link = document.createElement('a'); link.href = url;
      link.download = `protected-${report.filename.replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9._-]/g, '_')}${binary.mime.includes('pdf') ? '.pdf' : '.png'}`;
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1500);
      setNotice('Download requested. Once the file is saved, manually choose it on the demo portal, then submit.');
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Download blocked.'); }
  }

  const step = report ? verification?.status === 'passed_supported_checks' ? 3 : 2 : 1;
  return <div className="app">
    <header className="topbar"><a className="brand" href={BASE} target={inExtension ? '_blank' : undefined} rel="noreferrer"><span className="brand-symbol"><Icon name="shield" size={25}/></span><span>PrivacyGate<span className="brand-ai">AI</span></span></a><span className={`connection ${health ? 'connected' : ''}`}><span/>{health ? 'Local session' : 'Not paired'}</span></header>
    <main>
      <section className="intro"><div className="eyebrow">YOUR PRIVACY, BEFORE YOU UPLOAD</div><h1>A second look.<br/><span>A safer share.</span></h1><p>Understand what’s in your documents.<br/>Choose what you share.</p><div className="intro-shield" aria-hidden="true"><Icon name="shield" size={94}/><span>•••• •••• 0124</span></div><div className="intro-bottom"><span><Icon name="lock" size={14}/>On your computer</span><span><Icon name="check" size={14}/>Your approval, always</span></div></section>
      <div className="steps" aria-label="Protection steps">{['Add document', 'Review & approve', 'Save protected copy'].map((label, index) => <div className={step === index + 1 ? 'current' : step > index + 1 ? 'complete' : ''} key={label}><span>{step > index + 1 ? '✓' : index + 1}</span><strong>{label}</strong></div>)}</div>

      <details className="pairing card" open={!health}><summary><span><Icon name="lock" size={17}/>{health ? 'Backend paired · connection settings' : 'Connect to your local backend'}</span><span className="small-tag">LOOPBACK ONLY</span></summary><div className="pairing-content"><p>Run the backend, then paste the session token printed in its terminal. No cloud account is needed.</p><form onSubmit={connect}><label htmlFor="token">Backend session token</label><div className="token-row"><input id="token" type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} placeholder="Paste terminal token" required minLength={16}/><button className="button primary" disabled={pairing || busy}>{pairing ? 'Pairing…' : 'Pair'}</button></div></form>{health && <p className={health.ocr.available ? 'success-text' : 'warning-text'}>{health.ocr.available ? 'Tesseract OCR is ready. Documents are processed locally.' : health.ocr.error}</p>}<p className="tiny">{inExtension ? 'Token stored only in trusted extension session storage.' : 'Browser preview: token kept only in this page’s memory. Use the extension for the full portal workflow.'}</p></div></details>
      {error && <div className="alert error" role="alert"><Icon name="info"/><span>{error}</span></div>}
      {notice && <div className="alert notice" role="status"><Icon name="check"/><span>{notice}</span></div>}
      <div className="workspace">
        <div className="document-column">
          <section className="card upload-card"><div className="card-heading"><div><h2>Your document</h2><p>Your original stays untouched.</p></div><span className="small-tag">1 PAGE · 10 MB</span></div><label className={`dropzone ${dragging ? 'dragging' : ''} ${!health || busy ? 'inactive' : ''}`} onDragOver={event => {event.preventDefault(); if (health && !busy) setDragging(true);}} onDragLeave={() => setDragging(false)} onDrop={event => {event.preventDefault(); setDragging(false); const file = event.dataTransfer.files[0]; if (file) void inspect(file);}}><span className="upload-symbol"><Icon name="upload" size={25}/></span><strong>Drop a document here</strong><span>or <span className="purple-text">browse files</span></span><input ref={fileInput} type="file" accept=".pdf,.png,.jpg,.jpeg" disabled={!health || busy} onChange={event => {const file = event.target.files?.[0]; event.target.value = ''; if (file) void inspect(file);}}/><small>PDF, PNG, JPEG · inspected locally</small></label><div className="sample-picker"><label htmlFor="sample"><Icon name="sparkle" size={14}/>Just exploring?</label><div><select id="sample" value={sample} onChange={event => setSample(event.target.value)} disabled={busy}>{samples.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button className="button secondary" onClick={() => void useSample()} disabled={!health || busy}>Try sample</button></div></div>{report && <div className="file-summary"><span><Icon name="file"/></span><div><strong>{report.filename}</strong><small>{bytes(report.size)} · {report.classification}</small></div><button className="text-button" onClick={reset} disabled={busy}>Clear</button></div>}</section>

          <section className="card preview-card"><div className="card-heading"><div><h2>Document preview</h2><p>{variant === 'original' ? 'Original · never modified' : 'Output copy · inspect before sharing'}</p></div><div className="tabs"><button className={variant === 'original' ? 'active' : ''} disabled={!report || busy} onClick={() => report && void showPreview(report.session_id, false).catch(problem => setError(problem.message))}>Original</button><button className={variant === 'output' ? 'active' : ''} disabled={!verification || busy} onClick={() => report && void showPreview(report.session_id, true).catch(problem => setError(problem.message))}>Protected</button></div></div><div className="preview-stage">{preview ? <img src={preview} alt={`${variant === 'original' ? 'Original' : 'Protected'} document preview`}/> : <div className="empty-preview"><Icon name="file" size={52}/><strong>Your document will appear here</strong><p>Try a synthetic sample to explore the flow.</p></div>}{busy && <div className="processing" role="status"><span className="spinner"/><strong>{phase === 'analyzing' ? 'Inspecting locally' : phase === 'redacting' ? 'Redacting and checking output' : 'Preparing verified preview'}</strong><p>No document leaves this computer.</p></div>}</div><div className="preview-caption"><Icon name="lock" size={13}/>Private preview · single-page local session</div></section>
        </div>

        <div className="findings-column">
          <section className="card requirements-card"><div className="card-heading"><h2>Upload requirements</h2><span className="small-tag">DEMO PORTAL</span></div><div className="requirements-body"><div className="portal-name"><span><Icon name="file"/></span><div><strong>Scholarship application</strong><small>{requirements.source}</small></div></div><dl><div><dt>Accepted formats</dt><dd>{requirements.formats.map(format => format.toUpperCase()).join(', ')}</dd></div><div><dt>Maximum size</dt><dd>{bytes(requirements.max_bytes)}</dd></div><div><dt>Custom masking accepted</dt><dd className="warning-text">Not specified</dd></div></dl></div><p className="requirements-footnote"><Icon name="info" size={14}/>Technical checks cannot guarantee recipient acceptance.</p></section>

          <section className="card findings-card"><div className="card-heading"><h2>Privacy findings</h2><span className="count">{report ? report.findings.length : '—'}</span></div>{!report ? <div className="empty-findings"><span><Icon name="shield" size={31}/></span><strong>A little insight goes a long way.</strong><p>Personal details and your masking options will appear here.</p><div><span>ID numbers</span><span>Contact details</span></div></div> : <div className="findings-body"><div className="coverage">{report.processing_path === 'pdf_text' ? 'Native PDF text' : 'Local OCR'} · {report.elapsed_ms} ms · Rule-based</div>{report.limitations.map(limitation => <div className="alert warning" key={limitation}><Icon name="info" size={16}/><span>{limitation}</span></div>)}{!report.findings.length && <p className="no-findings">No supported identifier patterns found. This does not establish that the document is free of personal information.</p>}{report.findings.map(finding => <div className="finding" key={finding.id}><label><input type="checkbox" checked={selected.includes(finding.id)} disabled={busy || !report.can_redact || !finding.locatable} onChange={() => toggleFinding(finding)}/><span><strong>{finding.label}</strong><code>{finding.masked_value}</code></span><span className="finding-badge">{finding.recommended ? 'REVIEW' : 'YOUR CHOICE'}</span></label><p>{finding.reason}</p>{!finding.locatable && <p className="warning-text">Uncertain digit boundaries. Automatic masking is blocked.</p>}{finding.category === 'aadhaar' && <small>Checksum {finding.checksum_valid ? 'matches' : 'does not match'} · illustrative pattern, not identity verification</small>}</div>)}<div className={`alert ${report.authentication.signature_indicator || report.authentication.qr_status === 'detected' ? 'warning' : 'subtle'}`}><Icon name="info" size={16}/><span>{report.authentication.signature_indicator ? 'Signature indicator detected. All modification is blocked. Cryptographic validity was not checked.' : report.warnings[0]}</span></div><div className="technical-checks"><p className={report.compatibility.size_ok ? '' : 'error-text'}><Icon name={report.compatibility.size_ok ? 'check' : 'info'} size={15}/>{report.compatibility.size_ok ? 'Input size meets portal limit' : 'Input exceeds portal size limit'}</p><p className={report.compatibility.format_ok ? '' : 'error-text'}><Icon name={report.compatibility.format_ok ? 'check' : 'info'} size={15}/>{report.compatibility.format_ok ? 'Input format accepted' : 'Input format not accepted'}</p></div><label className="consent"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} disabled={busy || !selected.length}/><span>I approve masking the selected details in a new copy.</span></label><button className="button primary full" disabled={busy || !report.can_redact || !selected.length || !consent} onClick={() => void protect()}><Icon name="shield" size={18}/>Create protected copy</button><p className="action-note">You decide. Nothing is masked automatically.</p></div>}</section>

          {verification && <section className={`card verification-card ${verification.status === 'passed_supported_checks' ? 'passed' : 'blocked'}`}><div className="verification-icon"><Icon name={verification.status === 'passed_supported_checks' ? 'check' : 'info'} size={29}/></div><h2>{verification.status === 'passed_supported_checks' ? 'Protected copy ready' : 'Download blocked'}</h2><span className="verification-status">{verification.status.replaceAll('_', ' ')}</span><div className="verification-checks"><p><Icon name="file" size={16}/>{verification.approved_count} selected findings processed</p><p><Icon name={verification.checks.length && verification.checks.every(check => check.removed) ? 'check' : 'info'} size={16}/>Target-removal checks {verification.checks.length && verification.checks.every(check => check.removed) ? 'passed' : 'not passed'}</p><p><Icon name={verification.checks.length && verification.checks.every(check => check.replacement_rendered) ? 'check' : 'info'} size={16}/>Readable-mask checks {verification.checks.length && verification.checks.every(check => check.replacement_rendered) ? 'passed' : 'not passed'}</p><p><Icon name={verification.preserved_last_four ? 'check' : 'info'} size={16}/>Last-four preservation {selected.some(id => report?.findings.find(finding => finding.id === id)?.category === 'aadhaar') ? verification.preserved_last_four ? 'passed' : 'not passed' : 'not applicable'}</p><p><Icon name={verification.technical_compatibility ? 'check' : 'info'} size={16}/>Portal size/format {verification.technical_compatibility ? 'passed' : 'not passed'}</p></div><p className="verification-limitations">{verification.limitations}</p><button className="button primary full" onClick={() => void download()} disabled={busy || verification.status !== 'passed_supported_checks' || !verification.checks.length || !verification.checks.every(check => check.removed && check.replacement_rendered)}><Icon name="download" size={18}/>Download protected copy</button><a className="portal-link" href={`${BASE}/portal`} target="_blank" rel="noreferrer">Return to demo portal</a></section>}
        </div>
      </div>

      <details className="card activity"><summary><span><Icon name="activity" size={18}/>Behind the check</span><span className="small-tag">TWO RULE-BASED AGENTS</span></summary><div className="activity-body"><p>Bounded LangGraph workflows select local tools. No AI model or cloud API is called.</p>{report ? report.trace.map((entry, index) => <div className="trace-entry" key={index}><span><Icon name={entry.agent === 'Privacy Decision' ? 'shield' : 'file'} size={16}/></span><div><small>{entry.agent}</small><strong>{entry.tool}</strong><p>{entry.detail}</p></div></div>) : <p>Tool decisions appear after an inspection.</p>}</div></details>
      <footer><p><Icon name="lock" size={13}/>Built for privacy. Designed for your control.</p><div><span className={`phase ${busy ? 'working' : ''}`}>{phase}</span><span>Theme 2 · Local prototype</span></div><details><summary>Capabilities & limitations</summary><p>Single-page synthetic documents only. English OCR and supported patterns may miss information. No manual region selection, local LLMs, cryptographic verification, universal upload interception, or recipient acceptance guarantee. QR payloads remain unchanged. Your approval and passing output checks are always required.</p><p>Windows and macOS setup are documented. Windows checkpoints run here; macOS checkpoints are run afterward by the project’s Mac tester.</p></details></footer>
    </main>
  </div>;
}
