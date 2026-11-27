import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import test from 'node:test';

async function worker() {
  const calls = [], opened = [], settings = {};
  let listener;
  const runtime = {id: 'prototype-test-extension', getURL: path => `chrome-extension://prototype-test-extension/${path.replace(/^\//, '')}`,
    onMessage: {addListener: callback => {listener = callback;}}};
  const chrome = {runtime, storage: {session: {setAccessLevel: async value => {settings.accessLevel = value.accessLevel;},
    get: async () => settings, set: async value => {Object.assign(settings, value);}}},
    sidePanel: {setPanelBehavior: async () => {}, open: async value => {opened.push(value);}}};
  const context = vm.createContext({chrome, console, FormData, Blob, Uint8Array, AbortSignal, btoa, atob,
    fetch: async (url, options) => {
      calls.push({url, options});
      return new Response(JSON.stringify({status: 'ok', ocr: {available: true}}), {headers: {'content-type': 'application/json'}});
    }});
  const source = await readFile(new URL('../chrome-extension/.output/chrome-mv3/background.js', import.meta.url), 'utf8');
  vm.runInContext(source, context);
  return {calls, opened, settings, send: (message, sender) => listener(message, sender),
    panel: {id: runtime.id, url: runtime.getURL('/sidepanel.html')}, portal: {id: runtime.id, url: 'http://127.0.0.1:8765/portal', tab: {id: 7}}};
}

test('only trusted side-panel messages may pair or invoke the backend', async () => {
  const app = await worker();
  assert.equal(app.settings.accessLevel, 'TRUSTED_CONTEXTS');
  assert.equal(app.send({type: 'PG_PAIR', token: 'a-valid-length-test-token'}, app.portal), undefined);
  assert.equal(app.send({type: 'PG_API', payload: {operation: 'health'}}, app.portal), undefined);
  assert.equal(app.calls.length, 0);
  const paired = await app.send({type: 'PG_PAIR', token: 'a-valid-length-test-token'}, app.panel);
  assert.equal(paired.ok, true);
  assert.equal(app.calls[0].url, 'http://127.0.0.1:8765/health');
  assert.equal(app.calls[0].options.headers['X-PrivacyGate-Token'], 'a-valid-length-test-token');
  assert.equal(app.settings.backendToken, 'a-valid-length-test-token');
});

test('the backend proxy refuses unknown operations and missing pairing', async () => {
  const app = await worker();
  const unknown = await app.send({type: 'PG_API', payload: {operation: 'https://external.example'}}, app.panel);
  assert.equal(unknown.ok, false);
  const unpaired = await app.send({type: 'PG_API', payload: {operation: 'health'}}, app.panel);
  assert.equal(unpaired.ok, false);
  assert.equal(app.calls.length, 0);
});

test('only the controlled portal may open the side panel', async () => {
  const app = await worker();
  assert.equal(app.send({type: 'PG_OPEN'}, {...app.portal, url: 'https://untrusted.example/portal'}), undefined);
  assert.equal(app.opened.length, 0);
  const requirements = {formats: ['png'], max_bytes: 2097152, required_fields: []};
  const result = await app.send({type: 'PG_OPEN', requirements}, app.portal);
  assert.equal(result.ok, true);
  assert.equal(app.opened[0].tabId, 7);
  assert.equal(app.settings.portalRequirements.formats[0], 'png');
});
