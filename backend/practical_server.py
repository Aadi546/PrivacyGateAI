"""Run the practical workspace and its distinct-origin, local-only recipient."""
import asyncio
import uvicorn
from .main import app, receiver_app, TOKEN


async def serve():
    servers = [uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=port, access_log=False, log_level="warning"))
               for application, port in ((app, 8765), (receiver_app, 8766))]
    await asyncio.gather(*(server.serve() for server in servers))


if __name__ == "__main__":
    print("PrivacyGate practical demo: http://127.0.0.1:8765/practical", flush=True)
    print("Pairing token (local session only):", TOKEN, flush=True)
    print("Local recipient: 127.0.0.1:8766. Ctrl+C stops both servers.", flush=True)
    asyncio.run(serve())
