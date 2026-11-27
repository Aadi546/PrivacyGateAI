import {hydrateIcons} from './icons.js';
hydrateIcons();
const form = document.getElementById('portal-form');
const fileInput = document.getElementById('portal-file');
const status = document.getElementById('portal-file-status');
const success = document.getElementById('portal-success');

async function validateFile(file) {
  if (!file || !file.size) return 'Choose a non-empty protected document to continue.';
  if (file.size > Number(fileInput.dataset.maxBytes)) return 'This file exceeds the 2 MB limit. Choose a smaller document.';
  const raw = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  const pdf = new TextDecoder().decode(raw.slice(0, 5)) === '%PDF-';
  const png = raw[0] === 137 && raw[1] === 80 && raw[2] === 78 && raw[3] === 71 && raw[4] === 13 && raw[5] === 10 && raw[6] === 26 && raw[7] === 10;
  const jpeg = raw[0] === 255 && raw[1] === 216 && raw[2] === 255;
  if (!pdf && !png && !jpeg) return 'Choose a supported PDF, PNG, or JPEG. File signatures are checked.';
  return '';
}

fileInput.addEventListener('change', async () => {
  const file = fileInput.files[0];
  const error = await validateFile(file);
  status.textContent = error || `${file.name} · ${(file.size / 1024).toFixed(1)} KB · Not uploaded. This mock portal checks size and format; PrivacyGate checks the single-page limit.`;
  status.classList.toggle('error', Boolean(error));
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  const error = await validateFile(fileInput.files[0]);
  if (error) {
    status.textContent = error;
    status.classList.add('error');
    return;
  }
  form.hidden = true;
  success.hidden = false;
});

document.getElementById('restart-portal').addEventListener('click', () => {
  form.reset();
  fileInput.value = '';
  status.textContent = 'Choose your protected copy after inspecting it with PrivacyGate.';
  status.classList.remove('error');
  form.hidden = false;
  success.hidden = true;
});
