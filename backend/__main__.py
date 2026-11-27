"""Cross-platform local launcher. Credentials stay in this terminal and memory."""

import uvicorn
from .main import app, TOKEN

if __name__ == "__main__":
    print("\nPrivacyGate AI — local prototype")
    print("Open http://127.0.0.1:8765/portal")
    print("Pair the extension or local workspace with this session token:")
    print(TOKEN, flush=True)
    print("Keep this terminal open. Ctrl+C clears all document sessions.\n", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
