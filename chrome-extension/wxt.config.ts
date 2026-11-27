import { defineConfig } from 'wxt';
import identity from './extension-identity.json';

// See https://wxt.dev/api/reference/wxt/interfaces/inlineconfig.html
export default defineConfig({
  modules: ['@wxt-dev/module-react'],
  manifest: {
    name: 'PrivacyGate AI — Local Prototype',
    description: 'Inspect, approve, redact, and verify synthetic documents locally before uploading.',
    version: '0.2.0',
    key: identity.key,
    permissions: ['sidePanel', 'storage'],
    host_permissions: ['http://127.0.0.1:8765/*'],
    action: { default_title: 'Check with PrivacyGate' },
    content_security_policy: { extension_pages: "script-src 'self'; object-src 'self'; connect-src http://127.0.0.1:8765; img-src 'self' blob: data:;" },
  },
});
