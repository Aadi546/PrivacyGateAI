export default defineContentScript({
  matches: ['http://127.0.0.1:8765/portal*', 'http://localhost:8765/portal*'],
  main() {
    if (location.pathname !== '/portal') return;
    const input = document.querySelector<HTMLInputElement>('input[type="file"][data-privacygate]');
    if (!input || document.getElementById('privacygate-check')) return;
    const button = document.createElement('button');
    button.id = 'privacygate-check';
    button.type = 'button';
    button.className = 'button button-primary full-width';
    button.textContent = 'Check with PrivacyGate';
    button.addEventListener('click', () => {
      const formats = (input.dataset.formats || '').split(',').filter(format => ['pdf', 'png', 'jpeg'].includes(format));
      const limit = Number(input.dataset.maxBytes);
      if (!formats.length || !Number.isInteger(limit) || limit <= 0 || limit > 10 * 1024 * 1024) {
        button.textContent = 'Demo requirements are invalid';
        return;
      }
      void browser.runtime.sendMessage({type: 'PG_OPEN', requirements: {
        formats, max_bytes: limit,
        required_fields: (input.dataset.requiredFields || '').split(',').filter(field => ['aadhaar', 'pan', 'email', 'phone'].includes(field)),
        source: 'Mock portal data attributes',
      }}).catch(() => { button.textContent = 'Open PrivacyGate using the extension icon'; });
    });
    input.insertAdjacentElement('beforebegin', button);
  },
});
