// Shared approval gates. The API independently enforces the same protections.
export function initialState(epoch = 0) {
  return {epoch, stage: 1, connected: false, busy: '', file: null, report: null,
    context: null, selected: [], verification: null, changeConsent: false,
    uploadConsent: false, shareVariant: null, receipt: null, mode: 'cross_origin',
    originalPreview: '', outputPreview: '', sample: 'identity', comparisonMode: false,
    comparisonView: false, comparisonResult: null, selectedCandidate: null,
    candidates: [emptyCandidate(), emptyCandidate()]};
}

export function emptyCandidate() {
  return {file:null, report:null, context:null, preview:'', summary:null, acceptance:'unknown', requiredDetails:false, error:''};
}

export function candidateReady(candidate) {
  return Boolean(candidate.file && candidate.report && candidate.context && candidate.preview && !candidate.error);
}

export function clearComparisonSelection(state) {
  invalidateProtection(state);
  state.selected = [];
  state.selectedCandidate = null;
  state.file = null;
  state.report = null;
  state.context = null;
  state.originalPreview = '';
  state.outputPreview = '';
}

export function invalidateComparison(state) {
  clearComparisonSelection(state);
  state.comparisonResult = null;
}

export function invalidateProtection(state) {
  state.epoch++;
  state.verification = null;
  state.changeConsent = false;
  state.uploadConsent = false;
  state.shareVariant = null;
  state.receipt = null;
}

export function invalidateRecipient(state, mode) {
  state.epoch++;
  state.mode = mode;
  state.context = null;
  state.uploadConsent = false;
  state.receipt = null;
}

export function modificationBlocked(state) {
  return !state.report || state.report.authentication?.signature_indicator === true ||
    state.report.limitations?.some(text => text.includes('Unsupported PDF structures'));
}

export function hasChanges(state) {
  return state.selected.length > 0 || state.context?.hidden_information?.findings?.length > 0;
}

export function canProtect(state) {
  if (state.busy || !state.connected || !state.context || !state.changeConsent ||
      modificationBlocked(state) || !hasChanges(state)) return false;
  return state.selected.every(id => state.report.can_redact === true &&
    state.report.findings.some(f => f.id === id && f.locatable === true));
}

export function hasVerifiedCopy(state) {
  const proof = state.verification;
  if (!proof || proof.status !== 'passed_supported_checks' ||
      proof.original_unchanged !== true || proof.metadata_removed !== true ||
      proof.metadata_requested !== true || proof.technical_compatibility !== true ||
      !proof.output_digest || !proof.output_size || !Array.isArray(proof.checks)) return false;
  if (proof.pii_requested !== (state.selected.length > 0)) return false;
  if (proof.checks.length !== state.selected.length) return false;
  const ids = new Set(proof.checks.map(check => check.finding_id));
  return ids.size === state.selected.length && state.selected.every(id => ids.has(id)) &&
    proof.checks.every(check => check.removed === true && check.replacement_rendered === true);
}

export function canUpload(state) {
  return Boolean(state.connected && !state.busy && state.report && state.context &&
    state.uploadConsent && !state.receipt && state.report.compatibility?.size_ok === true &&
    state.report.compatibility?.format_ok === true &&
    (state.shareVariant === 'original' || (state.shareVariant === 'output' && hasVerifiedCopy(state))));
}

export function operationIsCurrent(state, epoch, sessionId) {
  return state.epoch === epoch && (!sessionId || state.report?.session_id === sessionId);
}

export function receiptMatches(receipt, grant) {
  return Boolean(receipt && receipt.upload_id === grant.upload_id &&
    receipt.destination === grant.upload_url && receipt.matching_approved_file === true &&
    receipt.body_retained === false && receipt.correlation_status === 'matched_controlled_session');
}
