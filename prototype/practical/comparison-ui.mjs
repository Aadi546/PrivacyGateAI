import {candidateReady} from './flow.mjs';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const disabled = value => value ? 'disabled' : '';
const titles = ['Government IDs and financial activity', 'Account identifiers', 'Contact and billing details', 'Metadata'];

export function comparisonChoose(s) {
  return `<section class="card compare-intro"><div><h2>Which address proof reveals less?</h2><p>Compare two alternatives before choosing one to protect and share.</p></div><button class="button primary" data-action="comparison-samples" ${disabled(!s.connected || s.busy)}>${s.busy === 'compare-inspect' ? 'Inspecting documents locally…' : 'Inspect bank statement + electricity bill'}</button><p class="small">Fictional samples only. Both contain the same name and address. You confirm suitability yourself.</p></section>
    <div class="comparison-inputs">${s.candidates.map((c, index) => `<section class="card"><div class="section-heading"><h2>Document ${index + 1}</h2>${candidateReady(c) ? '<span class="pill">Inspected</span>' : ''}</div><label class="field" for="candidate-file-${index}">Choose or replace this address proof</label><input id="candidate-file-${index}" data-candidate-file="${index}" type="file" accept=".pdf,.png,.jpg,.jpeg" ${disabled(!s.connected || s.busy)}><p class="small">${esc(c.file?.name || 'One-page PDF, PNG or JPEG · maximum 2 MB')}</p>${c.error ? `<p class="comparison-error" role="alert">${esc(c.error)}</p>` : ''}${c.file && !candidateReady(c) && !s.busy ? `<button class="text-button" data-action="retry-candidate" data-index="${index}">Retry inspection</button>` : ''}</section>`).join('')}</div>
    <div class="actions"><button class="text-button back" data-action="single-mode" ${disabled(s.busy)}>← Inspect one document instead</button>${s.candidates.every(candidateReady) ? `<button class="button primary" data-action="compare" ${disabled(s.busy)}>Compare documents →</button>` : ''}</div>`;
}

export function comparisonReview(s) {
  const result = s.comparisonResult;
  const recommendation = result?.recommended_session_id;
  const statusTitles = {recommended:'Less unnecessary disclosure under supported checks', only_confirmed_option:'Only one option is confirmed suitable',
    tie:'No privacy winner under this policy', inconclusive:'Comparison is inconclusive', no_confirmed_option:'Confirm which documents meet the requirement'};
  return `<p class="notice comparison-purpose"><strong>Purpose: address proof.</strong> Required name and current address are excluded from the disclosure comparison. Acceptance and suitability are your declarations.</p>
    <section class="card comparison-result ${recommendation ? 'passed' : ''}" aria-live="polite"><h2>${result ? statusTitles[result.status] : 'Suitability changed · compare again'}</h2><p>${esc(result?.reason || 'The previous recommendation and sharing approvals were cleared. Recalculate using your current declarations.')}</p>${result?.status === 'recommended' ? `<p class="comparison-winner">Suggested: ${esc(s.candidates.find(c => c.report.session_id === recommendation)?.file.name)}</p>` : ''}<p class="small">This compares detected categories, not every item of personal information. A lower count does not certify that a document is safe or valid.</p></section>
    <div class="comparison-cards">${s.candidates.map((c, index) => {
      const summary = c.summary;
      const recommended = recommendation === c.report?.session_id;
      return `<section class="card comparison-candidate ${recommended ? 'recommended' : ''}">
      <div class="section-heading"><h2>Document ${index + 1}</h2>${recommended ? `<span class="pill">${result.status === 'recommended' ? 'Suggested by policy' : 'Confirmed option'}</span>` : ''}</div><p class="comparison-filename">${esc(c.file?.name)}</p>
      ${c.preview ? `<img class="comparison-thumbnail" src="${c.preview}" alt="Original document ${index + 1}, page 1"><a class="small" href="${c.preview}" target="_blank" rel="noopener noreferrer">Open full-size original ${index + 1} preview</a>` : '<p class="notice">Inspection unavailable. Replace this file.</p>'}
      <div class="disclosure-groups">${summary ? titles.map((title, tier) => {
        const fields = summary.categories.filter(item => item.tier === tier);
        return `<div><h3>${title}</h3>${fields.length ? `<ul>${fields.map(item => `<li>${esc(item.label)}</li>`).join('')}</ul>` : '<p class="small">No supported patterns detected</p>'}</div>`;
      }).join('') : '<p class="small">Run comparison to view supported disclosure categories.</p>'}</div>
      ${summary?.limitations.length ? `<div class="warning"><strong>Coverage needs review</strong>${summary.limitations.map(item => `<p>${esc(item)}</p>`).join('')}</div>` : ''}
      ${summary?.signature_indicator ? '<div class="warning">Signature indicator detected. You can compare this document, but modification remains blocked.</div>' : ''}
      ${summary?.technical_compatibility === false ? '<div class="warning">This file does not meet the demo size/format requirements.</div>' : ''}
      <div class="field"><label for="acceptance-${index}">Does the recipient accept this document?</label><select id="acceptance-${index}" data-acceptance="${index}" ${disabled(s.busy)}><option value="unknown" ${c.acceptance === 'unknown' ? 'selected' : ''}>Unknown / not checked</option><option value="accepted" ${c.acceptance === 'accepted' ? 'selected' : ''}>Accepted under the recipient’s requirements</option><option value="not_accepted" ${c.acceptance === 'not_accepted' ? 'selected' : ''}>Not accepted</option></select></div>
      <label class="consent comparison-confirm"><input type="checkbox" data-required-details="${index}" ${c.requiredDetails ? 'checked' : ''} ${disabled(s.busy)}><span>I checked that this document shows the required name and current address.</span></label>
      <button class="button ${recommended ? 'primary' : 'secondary'}" data-action="choose-candidate" data-index="${index}" ${disabled(s.busy || !result || !candidateReady(c))}>Review document ${index + 1} for sharing →</button></section>`;
    }).join('')}</div>
    <details class="technical" id="comparison-policy"><summary>How the comparison works</summary><div class="technical-body"><p>Address-proof policy v1 compares distinct detected category counts in this priority order:</p><ol>${titles.map(title => `<li>${title}</li>`).join('')}</ol><p>The first differing tier determines the suggestion. File names and document types do not determine the winner. Blank headings and masked values do not count as readable financial evidence.</p><p>These are bounded English-text and metadata checks. Uncertain extraction or uninspected QR contents prevent a reliable privacy ranking. No document authenticity or recipient acceptance is verified.</p>${result?.differences.map((difference, index) => `<p><strong>Only detected in document ${index + 1}:</strong> ${esc(difference.unique_categories.join(', ') || 'No unique detected categories')}</p>`).join('') || ''}<p>Some comparison findings, such as transaction history or balances, do not yet support automatic masking in the protection step.</p></div></details>
    <div class="actions"><button class="text-button back" data-action="comparison-files" ${disabled(s.busy)}>← Replace documents</button><button class="button primary" data-action="compare" ${disabled(s.busy || !s.candidates.every(candidateReady))}>${s.busy === 'compare' ? 'Comparing locally…' : 'Compare documents again'}</button></div>`;
}
