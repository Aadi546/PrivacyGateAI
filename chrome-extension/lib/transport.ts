import { browser } from 'wxt/browser';
import type {ApiPayload, Binary, Reply} from './types';

export const BASE = 'http://127.0.0.1:8765';
export const inExtension = Boolean(browser?.runtime?.id);
let previewToken = '';

export function toBase64(buffer: ArrayBuffer) {
  const data = new Uint8Array(buffer);
  let result = '';
  for (let index = 0; index < data.length; index += 32768) result += String.fromCharCode(...data.subarray(index, index + 32768));
  return btoa(result);
}

export function binaryBlob(binary: Binary) {
  const text = atob(binary.base64);
  return new Blob([Uint8Array.from(text, character => character.charCodeAt(0))], {type: binary.mime});
}

export async function backendCall(payload: ApiPayload, token: string) {
  let path: string;
  const options: RequestInit = {headers: {'X-PrivacyGate-Token': token}, signal: AbortSignal.timeout(60000)};
  const session = encodeURIComponent(payload.session || '');
  if (payload.operation === 'health') path = '/health';
  else if (payload.operation === 'analyze') {
    path = '/api/analyze';
    const form = new FormData();
    form.append('file', binaryBlob({base64: payload.file || '', mime: 'application/octet-stream'}), payload.filename || 'document');
    form.append('requirements', JSON.stringify(payload.requirements));
    options.method = 'POST'; options.body = form;
  } else if (payload.operation === 'sample') path = `/api/sample/${encodeURIComponent(payload.sample || '')}`;
  else {
    if (!payload.session || !/^[A-Za-z0-9_-]+$/.test(payload.session)) throw new Error('Invalid inspection session.');
    if (payload.operation === 'redact') {
      path = `/api/sessions/${session}/redact`;
      options.method = 'POST';
      options.headers = {...options.headers, 'Content-Type': 'application/json'};
      options.body = JSON.stringify({finding_ids: payload.finding_ids || [], approved: true});
    } else if (payload.operation === 'preview') path = `/api/sessions/${session}/preview/0?variant=${payload.variant === 'output' ? 'output' : 'original'}`;
    else if (payload.operation === 'download') path = `/api/sessions/${session}/download`;
    else if (payload.operation === 'delete') { path = `/api/sessions/${session}`; options.method = 'DELETE'; }
    else throw new Error('Unsupported operation.');
  }
  const response = await fetch(BASE + path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'The local request failed. Try a supported single-page sample.');
  }
  if (['preview', 'download', 'sample'].includes(payload.operation)) {
    return {base64: toBase64(await response.arrayBuffer()), mime: response.headers.get('content-type') || 'application/octet-stream'} satisfies Binary;
  }
  return response.json();
}

export async function pair(token: string) {
  if (inExtension) {
    const reply: Reply = await browser.runtime.sendMessage({type: 'PG_PAIR', token});
    if (!reply.ok) throw new Error(reply.error || 'Pairing failed.');
    return reply.data;
  }
  const health = await backendCall({operation: 'health'}, token);
  previewToken = token;
  return health;
}

export async function api<T>(payload: ApiPayload): Promise<T> {
  if (inExtension) {
    const reply: Reply = await browser.runtime.sendMessage({type: 'PG_API', payload});
    if (!reply.ok) throw new Error(reply.error || 'The extension could not complete the request.');
    return reply.data as T;
  }
  if (!previewToken) throw new Error('Pair with the local backend first.');
  return backendCall(payload, previewToken) as Promise<T>;
}
