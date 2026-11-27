import test from 'node:test';
import assert from 'node:assert/strict';
import {initialState, invalidateProtection, invalidateRecipient, canProtect, hasVerifiedCopy,
  canUpload, operationIsCurrent, receiptMatches, invalidateComparison, clearComparisonSelection,
  candidateReady} from '../prototype/practical/flow.mjs';

function inspected() {
  return {...initialState(), connected:true,
    report:{session_id:'session-a', can_redact:true, authentication:{signature_indicator:false},
      limitations:[], findings:[{id:'email', locatable:true}], compatibility:{size_ok:true, format_ok:true}},
    context:{hidden_information:{findings:[{id:'pdf.author'}]}}, selected:['email']};
}
function verified() {
  return {...inspected(), verification:{status:'passed_supported_checks', original_unchanged:true,
    metadata_removed:true, metadata_requested:true, pii_requested:true, technical_compatibility:true,
    output_digest:'digest', output_size:500, checks:[{finding_id:'email', removed:true, replacement_rendered:true}]}};
}

test('protection and upload require separate explicit consent', () => {
  const s = inspected();
  assert.equal(canProtect(s), false);
  s.changeConsent = true;
  assert.equal(canProtect(s), true);
  s.shareVariant = 'original';
  assert.equal(canUpload(s), false);
  s.uploadConsent = true;
  assert.equal(canUpload(s), true);
});
test('an output cannot be uploaded based on the success label alone', () => {
  const s = verified();
  s.shareVariant = 'output'; s.uploadConsent = true;
  assert.equal(canUpload(s), true);
  for (const field of ['original_unchanged','metadata_removed','metadata_requested','technical_compatibility']) {
    s.verification[field] = false;
    assert.equal(canUpload(s), false, field);
    s.verification[field] = true;
  }
  s.verification.checks[0].replacement_rendered = false;
  assert.equal(canUpload(s), false);
});
test('failed, incomplete, missing and mismatched target checks block protected output', () => {
  for (const status of ['failed','incomplete']) {
    const s = verified(); s.verification.status = status;
    assert.equal(hasVerifiedCopy(s), false);
  }
  const s = verified();
  s.verification.checks[0].finding_id = 'different';
  assert.equal(hasVerifiedCopy(s), false);
  s.verification.checks = [];
  assert.equal(hasVerifiedCopy(s), false);
});
test('metadata-only protection works without invented identifier checks', () => {
  const s = verified();
  s.selected = []; s.verification.pii_requested = false; s.verification.checks = [];
  s.changeConsent = true;
  assert.equal(canProtect(s), true);
  assert.equal(hasVerifiedCopy(s), true);
  s.context.hidden_information.findings = [];
  assert.equal(canProtect(s), false);
});
test('signed documents and unsupported PDF structures block all modification', () => {
  const s = inspected(); s.changeConsent = true; s.selected = [];
  s.report.authentication.signature_indicator = true;
  assert.equal(canProtect(s), false);
  s.report.authentication.signature_indicator = false;
  s.report.limitations = ['Unsupported PDF structures: Embedded attachments'];
  assert.equal(canProtect(s), false);
});
test('uncertain locations cannot be approved for automatic masking', () => {
  const s = inspected(); s.changeConsent = true;
  s.report.findings[0].locatable = false;
  assert.equal(canProtect(s), false);
  s.selected = [];
  assert.equal(canProtect(s), true); // Only supported metadata cleanup remains.
});
test('changing a selection invalidates proof and both approvals, without falling back to original', () => {
  const s = verified(); const epoch = s.epoch;
  s.changeConsent = true; s.uploadConsent = true; s.shareVariant = 'output'; s.receipt = {};
  invalidateProtection(s);
  assert.equal(s.epoch, epoch + 1);
  assert.equal(s.verification, null);
  assert.equal(s.changeConsent, false);
  assert.equal(s.uploadConsent, false);
  assert.equal(s.shareVariant, null);
  assert.equal(s.receipt, null);
  assert.equal(canUpload(s), false);
});
test('recipient change clears evidence and consent but preserves valid document checks', () => {
  const s = verified();
  s.uploadConsent = true; s.shareVariant = 'output'; s.receipt = {};
  invalidateRecipient(s, 'same_origin');
  assert.equal(hasVerifiedCopy(s), true);
  assert.equal(s.uploadConsent, false);
  assert.equal(s.receipt, null);
  assert.equal(s.context, null);
  assert.equal(canUpload(s), false);
});
test('original upload must be chosen explicitly and still meet portal requirements', () => {
  const s = inspected(); s.uploadConsent = true;
  assert.equal(canUpload(s), false);
  s.shareVariant = 'original';
  assert.equal(canUpload(s), true);
  s.report.compatibility.size_ok = false;
  assert.equal(canUpload(s), false);
});
test('late responses cannot update a different inspection or revision', () => {
  const s = inspected();
  assert.equal(operationIsCurrent(s, 0, 'session-a'), true);
  invalidateProtection(s);
  assert.equal(operationIsCurrent(s, 0, 'session-a'), false);
  assert.equal(operationIsCurrent(s, 1, 'session-b'), false);
  assert.equal(operationIsCurrent(s, 1, 'session-a'), true);
});
test('receipt confirmation requires the same approval and recipient', () => {
  const grant = {upload_id:'upload-a', upload_url:'http://127.0.0.1:8766/mock-upload'};
  const receipt = {upload_id:grant.upload_id, destination:grant.upload_url,
    matching_approved_file:true, body_retained:false, correlation_status:'matched_controlled_session'};
  assert.equal(receiptMatches(receipt, grant), true);
  assert.equal(receiptMatches({...receipt, upload_id:'old-upload'}, grant), false);
  assert.equal(receiptMatches({...receipt, destination:'http://127.0.0.1:8765/mock-upload'}, grant), false);
  assert.equal(receiptMatches({...receipt, matching_approved_file:false}, grant), false);
});

test('changing comparison inputs invalidates the recommendation and every downstream approval', () => {
  const s = verified();
  s.comparisonResult = {recommended_session_id:'session-a'};
  s.selectedCandidate = 0; s.shareVariant = 'output'; s.uploadConsent = true; s.receipt = {};
  invalidateComparison(s);
  assert.equal(s.comparisonResult, null);
  assert.equal(s.selectedCandidate, null);
  assert.equal(s.report, null);
  assert.equal(s.context, null);
  assert.equal(s.verification, null);
  assert.equal(s.shareVariant, null);
  assert.equal(s.receipt, null);
  assert.equal(canUpload(s), false);
});
test('switching documents clears protected-copy state but can preserve a current comparison', () => {
  const s = verified(); s.comparisonResult = {status:'recommended'};
  s.file = {name:'old.pdf'}; s.originalPreview = 'blob:old'; s.outputPreview = 'blob:protected';
  clearComparisonSelection(s);
  assert.equal(s.comparisonResult.status, 'recommended');
  assert.equal(s.file, null);
  assert.equal(s.originalPreview, '');
  assert.equal(s.outputPreview, '');
  assert.equal(hasVerifiedCopy(s), false);
});
test('partially failed inspections cannot enter a comparison', () => {
  const candidate = {file:{},report:{},context:{},preview:'blob:preview',error:''};
  assert.equal(candidateReady(candidate),true);
  assert.equal(candidateReady({...candidate,context:null}),false);
  assert.equal(candidateReady({...candidate,error:'Failed to inspect'}),false);
});
