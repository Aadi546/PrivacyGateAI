import {backendCall} from '../lib/transport';
import {DEFAULT_REQUIREMENTS, type ApiPayload, type Reply} from '../lib/types';

export default defineBackground(() => {
  void browser.storage.session.setAccessLevel({accessLevel: 'TRUSTED_CONTEXTS'});
  void browser.sidePanel.setPanelBehavior({openPanelOnActionClick: true});
  browser.runtime.onMessage.addListener((message, sender) => {
    const isPanel = sender.id === browser.runtime.id && sender.url?.startsWith(browser.runtime.getURL('/sidepanel.html'));
    if (message?.type === 'PG_OPEN') {
      if (!sender.tab?.id || !/^http:\/\/(?:127\.0\.0\.1|localhost):8765\/portal(?:[?#]|$)/.test(sender.url || '')) return;
      // Call open immediately while the user gesture is active, before awaiting storage.
      const opening = browser.sidePanel.open({tabId: sender.tab.id});
      return (async () => {
        await browser.storage.session.set({portalRequirements: message.requirements || DEFAULT_REQUIREMENTS});
        await opening;
        return {ok: true};
      })();
    }
    if (!isPanel) return;
    return (async (): Promise<Reply> => {
      try {
        if (message.type === 'PG_PAIR') {
          if (typeof message.token !== 'string' || message.token.length < 16) throw new Error('Paste the complete token from the local backend terminal.');
          const data = await backendCall({operation: 'health'}, message.token);
          await browser.storage.session.set({backendToken: message.token});
          return {ok: true, data};
        }
        if (message.type === 'PG_API') {
          const payload = message.payload as ApiPayload;
          if (!['health', 'analyze', 'redact', 'preview', 'download', 'delete', 'sample'].includes(payload?.operation)) throw new Error('Unsupported operation.');
          if (payload.file && payload.file.length > 14 * 1024 * 1024) throw new Error('File exceeds the processing limit.');
          const {backendToken} = await browser.storage.session.get('backendToken');
          if (typeof backendToken !== 'string') throw new Error('Pair with the local backend first.');
          return {ok: true, data: await backendCall(payload, backendToken)};
        }
        throw new Error('Unsupported extension message.');
      } catch (error) { return {ok: false, error: error instanceof Error ? error.message : 'Local processing failed.'}; }
    })();
  });
});
