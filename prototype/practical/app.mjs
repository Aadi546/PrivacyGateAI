import {hydrateIcons} from '/static/icons.js';
import {initialState, invalidateProtection, invalidateRecipient, modificationBlocked, hasChanges,
  canProtect, hasVerifiedCopy, canUpload, operationIsCurrent, receiptMatches, emptyCandidate,
  candidateReady, invalidateComparison, clearComparisonSelection} from './flow.mjs';
import {comparisonChoose, comparisonReview} from './comparison-ui.mjs';

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const disabled = condition => condition ? 'disabled' : '';
const spinner = '<span class="loading-dot" aria-hidden="true"></span>';
const sampleNames = {identity:'identity-with-metadata.pdf', scan:'scanned-identity.png',
  photo:'photo-with-exif.jpg', clean:'enrolment-confirmation.pdf', signed:'signature-indicator.pdf'};
const sampleLabels = {identity:'Identity PDF + metadata', scan:'Scanned identity image',
  photo:'Image + EXIF metadata', clean:'Clean PDF', signed:'Signature indicator'};
let s = initialState();
let token = '';

async function api(path, options = {}) {
  const response = await fetch(path, {...options,
    headers:{'X-PrivacyGate-Token':token, ...options.headers},
    signal:AbortSignal.timeout(90000)});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return response;
}
const post = (path, body) => api(path, {method:'POST', headers:{'Content-Type':'application/json'},
  body:JSON.stringify(body)}).then(response => response.json());
const current = (epoch, sid) => operationIsCurrent(s, epoch, sid);
const hidden = () => s.context?.hidden_information?.findings || [];
const recipientName = () => s.mode === 'cross_origin' ? 'Separate local receiver · port 8766' : 'Same local receiver · port 8765';
const outputName = () => `privacygate-protected${s.verification?.mime === 'application/pdf' ? '.pdf' : '.png'}`;

function message(text = '', error = false) {
  $('#message').textContent = text;
  $('#message').className = text ? `message${error ? ' error' : ''}` : '';
}
function revoke(which) {
  if (s[which] && !s.candidates.some(c => c.preview === s[which])) URL.revokeObjectURL(s[which]);
  s[which] = '';
}
function reset(keepFile = false) {
  const previous = s;
  revoke('originalPreview');
  revoke('outputPreview');
  previous.candidates.forEach(candidate => { if (candidate.preview) URL.revokeObjectURL(candidate.preview); });
  s = {...initialState(previous.epoch + 1), connected:previous.connected,
    mode:previous.mode, sample:previous.sample, file:keepFile ? previous.file : null};
  const sessions = new Set([previous.report?.session_id, ...previous.candidates.map(c => c.report?.session_id)].filter(Boolean));
  sessions.forEach(sid => { void api(`/api/sessions/${sid}`, {method:'DELETE'}).catch(() => {}); });
  message();
  render();
}
function failure(error, epoch, sid) {
  if (!current(epoch, sid)) return;
  if (error.status === 401) {
    reset(true);
    token = '';
    s.connected = false;
    $('#pairing').open = true;
    message('Your local connection expired. Pair again, then inspect the document again.', true);
  } else if (error.status === 404) {
    reset(true);
    message('This inspection expired. Inspect the document again to continue.', true);
  } else {
    const text = error.name === 'TimeoutError' || error.name === 'AbortError'
      ? 'The local request timed out. Try again; the upload was not confirmed.'
      : error.message === 'Failed to fetch'
        ? 'Could not reach the local service. Check that both demo servers are running, then retry.'
        : error.message;
    message(text, true);
  }
}
function finish(epoch, sid) {
  if (current(epoch, sid)) { s.busy = ''; render(); }
}
function stageHeader(title, description) {
  return `<div class="stage-header"><div class="step-kicker">STEP ${s.stage} OF 4</div><h1 id="stage-title" tabindex="-1">${title}</h1><p>${description}</p></div>`;
}
function preview(which, label) {
  const url = s[which === 'output' ? 'outputPreview' : 'originalPreview'];
  return `<figure class="card preview"><figcaption><span>${label}</span><span>${which === 'output' ? 'Separate copy' : 'Unchanged source'}</span></figcaption>${url
    ? `<img src="${url}" alt="${label}, page 1">`
    : '<div class="notice">Preview unavailable. <button class="text-button" data-action="previews">Retry previews</button></div>'}</figure>`;
}
function warnings() {
  if (!s.report) return '';
  const auth = s.report.authentication || {};
  let text = '';
  if (auth.signature_indicator) text += '<div class="warning"><strong>Changes are blocked for this document.</strong>A signature indicator was found. Editing may invalidate it. Signature validity has not been checked.</div>';
  else if (modificationBlocked(s)) text += '<div class="warning"><strong>This document cannot be modified here.</strong>It has PDF structures the prototype cannot safely handle. Review the details or use a simpler source.</div>';
  else if (s.report.findings.length && !s.report.can_redact) text += '<div class="warning"><strong>Automatic masking is unavailable.</strong>The detected text cannot be located reliably enough. Review the original manually.</div>';
  if (auth.qr_status === 'detected') text += '<div class="warning"><strong>A possible QR code was detected.</strong>Its contents may still reveal information. This prototype leaves QR codes unchanged.</div>';
  if (s.report.compatibility?.size_ok !== true || s.report.compatibility?.format_ok !== true)
    text += '<div class="warning"><strong>Upload requirements are not met.</strong>Use a supported PDF, PNG or JPEG within the 2 MB limit.</div>';
  return text;
}
function recipient() {
  return `<section class="recipient"><h3>Intended recipient</h3><p>${recipientName()}</p><small>${s.receipt ? 'Confirmed by the local receiver receipt.' : 'Configured destination. Receipt confirms it only after upload.'}</small></section>`;
}
function technicalDetails() {
  if (!s.report) return '';
  const r = s.context?.recipient || {};
  const v = s.verification;
  return `<details class="technical" id="technical"><summary>Technical details</summary><div class="technical-body">
    <section><h3>Scope and limitations</h3><p>${esc(s.context?.hidden_information?.coverage || 'Recipient and metadata checks unavailable.')}</p>
    <p>Single-page files only. Pattern matches are not identity verification. A successful check does not guarantee anonymity, authenticity or acceptance by another portal.</p>
    <ul>${(s.report.limitations || []).map(text => `<li>${esc(text)}</li>`).join('')}</ul>
    <p>QR status: ${esc(s.report.authentication?.qr_status)}. Checks use local tools; no LLM is called.</p></section>
    <section><h3>Recipient evidence</h3><dl>
    <div><dt>Page origin</dt><dd>${esc(r.page_origin)}</dd></div>
    <div><dt>Declared destination</dt><dd>${esc(r.declared_destination)}</dd></div>
    <div><dt>Observed destination</dt><dd>${esc(r.observed_destination || 'Not observed yet')}</dd></div>
    <div><dt>Evidence source</dt><dd>${esc(r.evidence_source)}</dd></div></dl>
    <p>A different origin is a destination difference, not evidence of maliciousness. This controlled demo does not monitor arbitrary browser traffic.</p></section>
    <section><h3>Detection details</h3><ul>${s.report.findings.map(f => `<li>${esc(f.label)}: ${esc(f.reason)}</li>`).join('')}${hidden().map(f => `<li>${esc(f.label)}: ${esc(f.evidence)}</li>`).join('')}</ul></section>
    ${v ? `<section><h3>Verification results</h3><pre>${esc(JSON.stringify(v, null, 2))}</pre></section>` : ''}
    ${s.receipt ? `<section><h3>Receiver receipt</h3><pre>${esc(JSON.stringify(s.receipt, null, 2))}</pre></section>` : ''}
    </div></details>`;
}
function moreOptions(includeFiles = true) {
  return `<details class="more-options" id="more-options"><summary>More options${includeFiles ? ' · own file, other samples, recipient' : ' · change local recipient'}</summary><div class="options-body">
    ${includeFiles ? `<div class="field"><label for="sample-select">Other synthetic samples</label><div class="sample-controls"><select id="sample-select" ${disabled(s.busy)}>${Object.entries(sampleLabels).map(([key, label]) => `<option value="${key}" ${key === s.sample ? 'selected' : ''}>${label}</option>`).join('')}</select><button class="button secondary" data-action="other-sample" ${disabled(!s.connected || s.busy)}>Inspect sample</button></div></div>
    <div class="field"><label for="real-file">Choose a file to inspect</label><input id="real-file" type="file" accept=".pdf,.png,.jpg,.jpeg" ${disabled(!s.connected || s.busy)}><p class="small">Single-page PDF, PNG or JPEG · maximum 2 MB. Start with synthetic documents.</p></div>` : ''}
    <div class="field"><label for="recipient-mode">Local test destination</label><select id="recipient-mode" ${disabled(s.busy)}><option value="cross_origin" ${s.mode === 'cross_origin' ? 'selected' : ''}>Separate receiver · port 8766</option><option value="same_origin" ${s.mode === 'same_origin' ? 'selected' : ''}>Same receiver · port 8765</option></select><p class="small">Changing the destination clears upload approval and the previous receipt.</p></div>
  </div></details>`;
}
function chooseStage() {
  if (s.comparisonMode) return stageHeader('Compare two address proofs', 'Find the document with less unnecessary disclosure before you protect and share it.') + comparisonChoose(s);
  return stageHeader('Choose a document', 'See what the document reveals before sending it anywhere.') +
    `<section class="card choose-card"><div><h2>Try the sample identity PDF</h2><p>A fictional document with visible identifiers and hidden PDF properties. We will inspect the actual file on this computer.</p><button class="button primary" data-action="sample" ${disabled(!s.connected || s.busy)}>${s.busy === 'inspect' ? spinner + ' Inspecting locally…' : 'Inspect sample PDF →'}</button></div><span class="sample-symbol" data-icon="file-search" aria-hidden="true"></span></section>${moreOptions()}
    <section class="card compare-entry"><div><h2>Have two address-proof options?</h2><p class="small">Compare what each reveals, then choose one for sharing.</p></div><button class="button secondary" data-action="comparison-mode" ${disabled(!s.connected || s.busy)}>Compare two address proofs →</button></section>
    ${s.file && !s.busy ? `<div class="actions"><span class="small">${esc(s.file.name)}</span><button class="button secondary" data-action="inspect" ${disabled(!s.connected)}>Inspect selected file again</button></div>` : ''}`;
}
function reviewStage() {
  const blocked = modificationBlocked(s);
  const selectable = s.report.findings.filter(f => f.locatable && s.report.can_redact && !blocked);
  const comparisonNote = s.comparisonMode ? `<p class="notice comparison-purpose">Selected from your comparison: <strong>${esc(s.file.name)}</strong>. Only the supported identifiers below can be masked automatically. Other disclosed categories may remain.${s.candidates[s.selectedCandidate]?.acceptance !== 'accepted' || !s.candidates[s.selectedCandidate]?.requiredDetails ? ' You have not confirmed that this document meets the recipient’s requirements.' : ''}</p>` : '';
  return stageHeader('Review what the file reveals', 'Select the details you want to mask. Nothing is changed or sent at this step.') + comparisonNote + warnings() +
    `<div class="two-col">${preview('original', 'Original document')}<div class="card review-card">
    <section><div class="section-heading"><h2>Visible identifiers</h2><span class="count">${s.report.findings.length} matches</span></div>
    ${selectable.length ? `<button class="text-button" data-action="select-all" ${disabled(s.busy)}>${selectable.every(f => s.selected.includes(f.id)) ? 'Clear selection' : 'Select all supported matches'}</button>` : ''}
    <div class="finding-list">${s.report.findings.map(f => `<label class="finding"><input type="checkbox" data-finding="${esc(f.id)}" aria-label="Mask ${esc(f.label)}" ${s.selected.includes(f.id) ? 'checked' : ''} ${disabled(s.busy || blocked || !s.report.can_redact || !f.locatable)}><span class="finding-text"><span><strong>${esc(f.label)}</strong><small>${f.locatable && s.report.can_redact && !blocked ? 'Select to mask' : 'Manual review needed'}</small></span><span class="mask">${esc(f.masked_value)}</span></span></label>`).join('') ||
      '<p class="notice">No supported identifier patterns found. Review the preview for other personal information.</p>'}</div></section>
    <section><div class="section-heading"><h2>Hidden file details</h2><span class="count">${hidden().length} fields</span></div>
    ${hidden().length ? `<ul class="metadata-list">${hidden().map(f => `<li>${esc(f.label)}</li>`).join('')}</ul><p class="small">Not visible in the page preview. Supported metadata will be removed if you approve a protected copy.</p>` : '<p class="small">No supported metadata fields found.</p>'}</section>
    ${recipient()}${!s.context ? '<button class="button secondary" data-action="recipient-retry">Retry recipient check</button>' : ''}</div></div>
    <div class="actions"><button class="text-button back" data-action="${s.comparisonMode ? 'back-comparison' : 'start'}">${s.comparisonMode ? '← Compare documents' : '← Choose another file'}</button>
    <button class="text-button" data-action="original" ${disabled(s.busy || !s.context)}>Continue with unchanged original</button>
    ${!blocked && hasChanges(s) ? `<button class="button primary" data-action="review-protection" ${disabled(s.busy || !s.originalPreview || !s.context)}>Review protection →</button>` : ''}</div>${technicalDetails()}`;
}
function protectionStage() {
  if (hasVerifiedCopy(s)) return stageHeader('Compare the protected copy', 'Only the approved changes were applied. Check the result before sharing.') + warnings() +
    `<div class="comparison">${preview('original', 'Original document')}${preview('output', 'Protected document')}</div>
    <section class="card passed verification-summary"><div class="success-title"><span class="check-circle">✓</span>Supported checks passed</div><ul class="checks">${s.selected.length ? `<li>${s.selected.length} selected ${s.selected.length === 1 ? 'detail' : 'details'} checked</li>` : ''}<li>Metadata cleanup checked</li><li>Original unchanged</li></ul></section>
    <p class="small">Other content, including unselected details, may remain in the copy.</p>
    <div class="actions"><button class="text-button back" data-action="review">← Edit selection</button><button class="button secondary" data-action="download" ${disabled(s.busy)}>Download protected copy</button><button class="button primary" data-action="to-upload" ${disabled(s.busy || !s.outputPreview)}>Continue to upload →</button></div>${technicalDetails()}`;
  const chosen = s.report.findings.filter(f => s.selected.includes(f.id));
  return stageHeader('Approve the protected copy', 'Review the changes. Your original will stay unchanged.') + warnings() +
    `<section class="card protection-review"><h2>Changes to a separate copy</h2><ul class="summary-list">
    ${chosen.map(f => `<li>Mask ${esc(f.label)} as <strong>${esc(f.masked_value)}</strong>.</li>`).join('')}
    <li>${hidden().length ? 'Remove ' + hidden().length + ' supported metadata fields.' : 'Remove any supported metadata from the output.'}</li></ul>
    <p class="small">Unselected details and other document content remain.</p>
    ${s.verification ? '<div class="warning"><strong>Verification did not pass.</strong>Protected download and upload are blocked. Review your selection or try a clearer document.</div>' : ''}
    <div class="warning" id="recipient-requirements-notice"><strong>Check what the recipient needs before making changes</strong><p>The recipient may require the complete document, including details beyond the main ID number. Other information may be used for verification even when it is not mentioned on the upload page.</p><p>You are responsible for checking which details must stay visible and whether a modified copy will be accepted. If the requirements are unclear, ask the recipient before masking or removing information. PrivacyGate does not guarantee acceptance.</p></div>
    <label class="consent"><input id="change-consent" type="checkbox" aria-describedby="recipient-requirements-notice" ${s.changeConsent ? 'checked' : ''} ${disabled(s.busy || modificationBlocked(s))}><span>I understand that required details must be preserved and approve ${s.selected.length ? 'these selected masks and ' : ''}supported metadata removal in a separate copy.</span></label>
    <div class="inline-actions"><button class="button primary" data-action="protect" ${disabled(!canProtect(s))}>${s.busy === 'protect' ? spinner + ' Protecting and verifying…' : 'Create and verify protected copy'}</button><button class="text-button" data-action="review" ${disabled(s.busy)}>← Edit selection</button></div></section>${technicalDetails()}`;
}
function uploadStage() {
  const protectedCopy = s.shareVariant === 'output';
  if (s.receipt) return stageHeader('Upload confirmed', 'The local receiver matched the file you approved.') +
    `<section class="card passed receipt"><div class="success-title"><span class="check-circle">✓</span>Local test upload complete</div><p>The receiver checked the approved file and discarded the received document body.</p><div class="receipt-grid"><div><small>File received</small><strong>${protectedCopy ? 'Verified protected copy' : 'Unchanged original'}</strong>${s.comparisonMode ? `<small>Source: ${esc(s.file.name)}</small>` : ''}</div><div><small>Confirmed destination</small><strong>${recipientName()}</strong></div></div><ul class="checks"><li>Received file matched the approved bytes</li><li>Receiver retained no document body</li></ul><div class="actions"><button class="button primary" data-action="start">Start again</button></div></section>${technicalDetails()}`;
  return stageHeader('Approve the local test upload', 'Check the exact copy and destination. This approval is separate from changing the document.') + warnings() +
    `<section class="card send-card"><h2>Ready for your review</h2><div class="share-file"><span data-icon="file"></span><div><strong>${protectedCopy ? 'Verified protected copy' : 'Unchanged original'}</strong><p>${esc(protectedCopy ? outputName() : s.file.name)}</p>${s.comparisonMode ? `<p>Source: ${esc(s.file.name)}</p>` : ''}</div>${protectedCopy ? '<span class="pill">Checks passed</span>' : ''}</div>
    ${!protectedCopy ? '<div class="warning"><strong>You chose the original.</strong>No masking or metadata cleanup will be applied to the file being sent.</div>' : '<p class="small">This is the separate copy you just reviewed. Unselected information may still be present.</p>'}
    ${recipient()}${!s.context ? '<button class="button secondary" data-action="recipient-retry">Retry recipient check</button>' : ''}
    <label class="consent"><input id="upload-consent" type="checkbox" ${s.uploadConsent ? 'checked' : ''} ${disabled(s.busy || !s.context || (protectedCopy && !hasVerifiedCopy(s)))}><span>I approve sending the <strong>${protectedCopy ? 'verified protected copy' : 'unchanged original'}</strong> to the local receiver shown above.</span></label>
    <button class="button primary" data-action="submit" ${disabled(!canUpload(s))}>${s.busy === 'submit' ? spinner + ' Sending to local receiver…' : 'Upload ' + (protectedCopy ? 'protected copy' : 'original') + ' locally'}</button>
    <div class="actions"><button class="text-button back" data-action="${protectedCopy ? 'compare' : 'review'}" ${disabled(s.busy)}>← Back to review</button></div></section>${moreOptions(false)}${technicalDetails()}`;
}
function render(focus) {
  const opened = [...document.querySelectorAll('#workspace details[open]')].map(node => node.id);
  const names = [s.comparisonMode ? 'Choose two documents' : 'Choose document', s.comparisonMode ? 'Compare & review' : 'Review findings', 'Protect & verify', 'Approve upload'];
  $('#progress').innerHTML = names.map((name, index) => {
    const skipped = index === 2 && s.stage === 4 && s.shareVariant === 'original';
    const done = !skipped && s.stage > index + 1;
    return `<li class="${s.stage === index + 1 ? 'active' : done ? 'done' : ''}" ${s.stage === index + 1 ? 'aria-current="step"' : ''}><span class="number">${skipped ? '–' : done ? '✓' : index + 1}</span><span>${skipped ? 'Protection skipped' : name}</span></li>`;
  }).join('');
  $('#workspace').innerHTML = s.stage === 1 ? chooseStage() : s.stage === 2 ? (s.comparisonMode && s.comparisonView ? stageHeader('Choose what to share', 'Compare supported disclosures and confirm the recipient’s requirements. You make the final choice.') + comparisonReview(s) : reviewStage()) : s.stage === 3 ? protectionStage() : uploadStage();
  opened.forEach(id => { if ($('#' + id)) $('#' + id).open = true; });
  $('#connection').textContent = s.connected ? 'Connected · local processing' : 'Connect to begin';
  $('#connection').classList.toggle('connected', s.connected);
  $('#pair-summary').textContent = s.connected ? 'Local backend connected' : 'Connect to your local backend';
  $('#connect').disabled = s.busy === 'pair';
  hydrateIcons();
  if (focus) $(focus)?.focus({preventScroll:true});
}
function go(stage) {
  s.stage = stage;
  s.uploadConsent = false;
  message();
  render();
  $('#stage-title')?.focus({preventScroll:true});
  window.scrollTo({top:0, behavior:'instant'});
}
async function fetchPreview(which, epoch, sid) {
  const response = await api(`/api/sessions/${sid}/preview/0?variant=${which}`);
  const blob = await response.blob();
  if (!current(epoch, sid)) return;
  const key = which === 'output' ? 'outputPreview' : 'originalPreview';
  revoke(key);
  s[key] = URL.createObjectURL(blob);
}
async function inspect(source, sampleKind) {
  if (!s.connected || s.busy) return;
  reset(Boolean(source));
  const epoch = s.epoch;
  s.busy = 'inspect';
  render();
  let sid;
  try {
    if (sampleKind) {
      const response = await api(`/api/practical/samples/${sampleKind}`);
      const blob = await response.blob();
      if (!current(epoch)) return;
      source = new File([blob], sampleNames[sampleKind], {type:blob.type});
    }
    if (!source) throw new Error('Choose a document first.');
    s.file = source;
    const form = new FormData();
    form.append('file', source);
    form.append('requirements', JSON.stringify({formats:['pdf','png','jpeg'], max_bytes:2097152, required_fields:[]}));
    const report = await api('/api/analyze', {method:'POST', body:form}).then(response => response.json());
    sid = report.session_id;
    if (!current(epoch)) {
      void api(`/api/sessions/${sid}`, {method:'DELETE'}).catch(() => {});
      return;
    }
    s.report = report;
    const context = await post(`/api/practical/sessions/${sid}/context`, {page_origin:location.origin, mode:s.mode});
    if (!current(epoch, sid)) return;
    s.context = context;
    await fetchPreview('original', epoch, sid);
    if (!current(epoch, sid)) return;
    s.busy = '';
    go(2);
  } catch (error) {
    if (current(epoch, sid)) {
      failure(error, epoch, sid);
      // An incomplete inspection must not unlock review or submission.
      if (current(epoch, sid)) {
        const text = $('#message').textContent;
        reset(true);
        message(text, true);
      }
    }
  } finally { finish(epoch, sid); }
}
async function protect() {
  if (!canProtect(s)) return;
  const epoch = s.epoch, sid = s.report.session_id, ids = [...s.selected];
  s.busy = 'protect';
  s.uploadConsent = false;
  s.receipt = null;
  s.shareVariant = null;
  s.verification = null;
  revoke('outputPreview');
  message();
  render();
  try {
    const result = await post(`/api/practical/sessions/${sid}/protect`,
      {finding_ids:ids, remove_metadata:true, approved:true});
    if (!current(epoch, sid)) return;
    s.verification = result.verification;
    if (!hasVerifiedCopy(s)) throw new Error('Supported verification checks did not pass. Protected download and upload are blocked.');
    s.shareVariant = 'output';
    await fetchPreview('output', epoch, sid);
    if (current(epoch, sid)) message();
  } catch (error) { failure(error, epoch, sid); }
  finally {
    if (current(epoch, sid)) s.changeConsent = false;
    finish(epoch, sid);
  }
}
async function retryPreviews() {
  if (!s.report || s.busy) return;
  const epoch = s.epoch, sid = s.report.session_id;
  s.busy = 'preview'; render();
  try {
    await fetchPreview('original', epoch, sid);
    if (current(epoch, sid) && hasVerifiedCopy(s)) await fetchPreview('output', epoch, sid);
    if (current(epoch, sid)) message();
  } catch (error) { failure(error, epoch, sid); }
  finally { finish(epoch, sid); }
}
async function download() {
  if (!hasVerifiedCopy(s) || s.busy) return;
  const epoch = s.epoch, sid = s.report.session_id, name = outputName();
  s.busy = 'download'; render();
  try {
    const response = await api(`/api/practical/sessions/${sid}/download`);
    const blob = await response.blob();
    if (!current(epoch, sid)) return;
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    message('Protected copy download requested.');
  } catch (error) { failure(error, epoch, sid); }
  finally { finish(epoch, sid); }
}
async function submit() {
  if (!canUpload(s)) return;
  const epoch = s.epoch, sid = s.report.session_id;
  const choice = s.shareVariant, mode = s.mode, original = s.file;
  s.busy = 'submit'; message(); render();
  try {
    const grant = await post(`/api/practical/sessions/${sid}/upload-approval`,
      {page_origin:location.origin, mode, variant:choice, approved:true});
    if (!current(epoch, sid)) return;
    const blob = choice === 'output' ? await api(`/api/practical/sessions/${sid}/download`).then(response => response.blob()) : original;
    if (!current(epoch, sid)) return;
    const response = await fetch(grant.upload_url, {method:'POST',
      headers:{'Content-Type':'application/octet-stream', 'X-PrivacyGate-Upload-Grant':grant.grant},
      body:blob, signal:AbortSignal.timeout(30000)});
    const result = await response.json();
    if (!current(epoch, sid)) return;
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The local upload failed.');
    if (!receiptMatches(result, grant)) throw new Error('The receipt did not match this approved upload. Upload confirmation is unavailable.');
    s.receipt = result;
    s.context.recipient.observed_destination = result.destination;
    s.context.recipient.receipt = result;
    s.context.recipient.evidence_source = result.evidence_source;
    message();
  } catch (error) { failure(error, epoch, sid); }
  finally {
    if (current(epoch, sid)) s.uploadConsent = false;
    finish(epoch, sid);
  }
}
async function changeRecipient(mode) {
  if (s.busy || (mode === s.mode && s.context)) return;
  invalidateRecipient(s, mode);
  message();
  if (!s.report) { render('#recipient-mode'); return; }
  const epoch = s.epoch, sid = s.report.session_id;
  s.busy = 'context'; render();
  try {
    const context = await post(`/api/practical/sessions/${sid}/context`, {page_origin:location.origin, mode});
    if (!current(epoch, sid)) return;
    s.context = context;
    message('Destination updated. Review it and approve this upload again.');
  } catch (error) { failure(error, epoch, sid); }
  finally { finish(epoch, sid); }
}
function changeSelection(ids, focus) {
  revoke('outputPreview');
  invalidateProtection(s);
  s.selected = ids;
  message();
  render(focus);
}

function clearActiveCandidate(invalidateResult = false) {
  revoke('outputPreview'); revoke('originalPreview');
  if (invalidateResult) invalidateComparison(s); else clearComparisonSelection(s);
}
async function clearCandidateOutputs(epoch) {
  for (const candidate of s.candidates) {
    if (!candidate.report || !current(epoch)) continue;
    await post(`/api/practical/sessions/${candidate.report.session_id}/clear-protection`, {});
  }
}
async function analyzeCandidate(index, source, epoch, sampleKind) {
  let sid;
  try {
    if (sampleKind) {
      const response = await api(`/api/practical/samples/${sampleKind}`);
      const blob = await response.blob();
      if (!current(epoch)) return;
      source = new File([blob], sampleKind === 'bank' ? 'fictional-bank-statement.pdf' : 'fictional-electricity-bill.pdf', {type:blob.type});
    }
    if (!current(epoch)) return;
    s.candidates[index].file = source;
    render();
    const form = new FormData();
    form.append('file', source);
    form.append('requirements', JSON.stringify({formats:['pdf','png','jpeg'], max_bytes:2097152, required_fields:[]}));
    const report = await api('/api/analyze', {method:'POST', body:form}).then(r => r.json());
    sid = report.session_id;
    if (!current(epoch)) { void api(`/api/sessions/${sid}`, {method:'DELETE'}).catch(() => {}); return; }
    s.candidates[index].report = report;
    const context = await post(`/api/practical/sessions/${sid}/context`, {page_origin:location.origin, mode:s.mode});
    const response = await api(`/api/sessions/${sid}/preview/0?variant=original`);
    const blob = await response.blob();
    if (!current(epoch)) return;
    s.candidates[index].context = context;
    s.candidates[index].preview = URL.createObjectURL(blob);
  } catch (error) {
    if (!current(epoch)) return;
    if (error.status === 401) throw error;
    s.candidates[index].error = error.message;
    if (sid) {
      void api(`/api/sessions/${sid}`, {method:'DELETE'}).catch(() => {});
      s.candidates[index].report = null;
    }
  }
}
async function inspectComparison(index, source, samplePair = false) {
  if (!s.connected || s.busy) return;
  if (samplePair) { reset(); s.comparisonMode = true; }
  clearActiveCandidate(true);
  s.comparisonView = false; s.stage = 1;
  const epoch = s.epoch;
  s.busy = 'compare-inspect'; message(); render();
  try {
    await clearCandidateOutputs(epoch);
    if (!current(epoch)) return;
    if (!samplePair) {
      const old = s.candidates[index];
      if (old.preview) URL.revokeObjectURL(old.preview);
      if (old.report) await api(`/api/sessions/${old.report.session_id}`, {method:'DELETE'});
      if (!current(epoch)) return;
      s.candidates[index] = {...emptyCandidate(), file:source};
      await analyzeCandidate(index, source, epoch);
    } else {
      await analyzeCandidate(0, null, epoch, 'bank');
      if (current(epoch)) await analyzeCandidate(1, null, epoch, 'utility');
    }
    if (!current(epoch)) return;
    s.busy = ''; render();
    if (s.candidates.every(candidateReady)) await compareDocuments();
  } catch (error) { failure(error, epoch); }
  finally { finish(epoch); }
}
async function compareDocuments() {
  if (s.busy || !s.candidates.every(candidateReady)) return;
  clearActiveCandidate(true);
  const epoch = s.epoch;
  s.busy = 'compare'; message(); render();
  try {
    const result = await post('/api/practical/compare', {candidates:s.candidates.map(c => ({
      session_id:c.report.session_id, acceptance:c.acceptance, required_details_confirmed:c.requiredDetails}))});
    if (!current(epoch)) return;
    s.comparisonResult = result;
    result.candidates.forEach(summary => { s.candidates.find(c => c.report.session_id === summary.session_id).summary = summary; });
    s.comparisonView = true; s.busy = ''; go(2);
  } catch (error) { failure(error, epoch); }
  finally { finish(epoch); }
}
async function updateSuitability(index, field, value, focus) {
  clearActiveCandidate(true);
  s.candidates[index][field] = value;
  s.comparisonView = true; s.stage = 2;
  const epoch = s.epoch;
  s.busy = 'candidate-update'; message(); render(focus);
  try { await clearCandidateOutputs(epoch); }
  catch (error) { failure(error, epoch); }
  finally { finish(epoch); if (current(epoch)) $(focus)?.focus({preventScroll:true}); }
}
async function chooseCandidate(index) {
  if (!s.comparisonResult || !candidateReady(s.candidates[index]) || s.busy) return;
  clearActiveCandidate();
  const epoch = s.epoch;
  s.busy = 'choose-candidate'; message(); render();
  try {
    await clearCandidateOutputs(epoch);
    if (!current(epoch)) return;
    const candidate = s.candidates[index];
    const context = await post(`/api/practical/sessions/${candidate.report.session_id}/context`, {page_origin:location.origin, mode:s.mode});
    if (!current(epoch)) return;
    s.file = candidate.file; s.report = candidate.report; s.context = context;
    s.originalPreview = candidate.preview; s.selectedCandidate = index;
    s.comparisonView = false; s.busy = ''; go(2);
  } catch (error) { failure(error, epoch); }
  finally { finish(epoch); }
}
async function returnToComparison(files = false) {
  clearActiveCandidate();
  const epoch = s.epoch;
  s.comparisonView = !files; s.stage = files ? 1 : 2;
  s.busy = 'candidate-update'; message(); render();
  try { await clearCandidateOutputs(epoch); }
  catch (error) { failure(error, epoch); }
  finally { finish(epoch); }
}

$('#pair-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (s.busy) return;
  reset(true);
  const epoch = s.epoch;
  token = $('#pair-token').value.trim();
  $('#pair-token').value = '';
  s.busy = 'pair'; render();
  try {
    const health = await api('/health').then(response => response.json());
    if (!current(epoch)) return;
    s.connected = true;
    $('#pairing').open = false;
    message(health.ocr.available ? '' : 'Connected. OCR is unavailable; scanned documents may be limited.');
  } catch (error) {
    if (current(epoch)) { token = ''; s.connected = false; message(error.message, true); }
  } finally { finish(epoch); }
});
$('#reset').addEventListener('click', () => reset());
document.addEventListener('click', async event => {
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled) return;
  const action = button.dataset.action;
  if (action === 'start') { reset(); return; }
  if (s.busy) return;
  if (action === 'comparison-mode') { reset(); s.comparisonMode = true; render(); }
  else if (action === 'single-mode') reset();
  else if (action === 'comparison-samples') await inspectComparison(null, null, true);
  else if (action === 'retry-candidate') await inspectComparison(Number(button.dataset.index), s.candidates[Number(button.dataset.index)].file);
  else if (action === 'compare') await compareDocuments();
  else if (action === 'choose-candidate') await chooseCandidate(Number(button.dataset.index));
  else if (action === 'back-comparison') await returnToComparison();
  else if (action === 'comparison-files') await returnToComparison(true);
  else if (action === 'sample') await inspect(null, 'identity');
  else if (action === 'other-sample') await inspect(null, s.sample);
  else if (action === 'inspect') await inspect(s.file);
  else if (action === 'select-all') {
    const ids = s.report.findings.filter(f => f.locatable && s.report.can_redact && !modificationBlocked(s)).map(f => f.id);
    changeSelection(ids.every(id => s.selected.includes(id)) ? [] : ids, '[data-action="select-all"]');
  } else if (action === 'review-protection' && hasChanges(s) && !modificationBlocked(s)) go(3);
  else if (action === 'review') go(2);
  else if (action === 'compare' && hasVerifiedCopy(s)) go(3);
  else if (action === 'original' && s.context && s.originalPreview) { s.shareVariant = 'original'; go(4); }
  else if (action === 'to-upload' && hasVerifiedCopy(s) && s.outputPreview) { s.shareVariant = 'output'; go(4); }
  else if (action === 'protect') await protect();
  else if (action === 'download') await download();
  else if (action === 'submit') await submit();
  else if (action === 'previews') await retryPreviews();
  else if (action === 'recipient-retry') await changeRecipient(s.mode);
});
document.addEventListener('change', async event => {
  const el = event.target;
  if (s.busy) return;
  if (el.matches('[data-candidate-file]') && el.files[0]) {
    const source = el.files[0];
    if (!source.size || source.size > 2097152) { el.value = ''; message('Choose a non-empty single-page PDF, PNG or JPEG no larger than 2 MB. The previous candidate was kept.', true); return; }
    await inspectComparison(Number(el.dataset.candidateFile), source);
  } else if (el.matches('[data-acceptance]')) {
    await updateSuitability(Number(el.dataset.acceptance), 'acceptance', el.value, `#${el.id}`);
  } else if (el.matches('[data-required-details]')) {
    await updateSuitability(Number(el.dataset.requiredDetails), 'requiredDetails', el.checked, `[data-required-details="${el.dataset.requiredDetails}"]`);
  } else if (el.id === 'real-file' && el.files[0]) {
    const source = el.files[0];
    if (!source.size || source.size > 2097152) {
      el.value = ''; message('Choose a non-empty PDF, PNG or JPEG no larger than 2 MB.', true); return;
    }
    await inspect(source);
  } else if (el.matches('[data-finding]')) {
    const finding = s.report?.findings.find(f => f.id === el.dataset.finding);
    if (!finding?.locatable || !s.report.can_redact || modificationBlocked(s)) return;
    changeSelection(el.checked ? [...s.selected, finding.id] : s.selected.filter(id => id !== finding.id),
      `[data-finding="${finding.id}"]`);
  } else if (el.id === 'change-consent') {
    s.changeConsent = el.checked; render('#change-consent');
  } else if (el.id === 'upload-consent') {
    s.uploadConsent = el.checked; render('#upload-consent');
  } else if (el.id === 'sample-select') s.sample = el.value;
  else if (el.id === 'recipient-mode') await changeRecipient(el.value);
});
render();
