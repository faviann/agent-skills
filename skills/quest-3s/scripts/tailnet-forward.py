#!/usr/bin/env python3
"""Forward 127.0.0.1:<local-port> to a tailnet host:port through `tailscale nc`.

For hosts whose tailscaled runs with --tun=userspace-networking: ordinary sockets
(adb included) can't reach tailnet IPs there, but `tailscale nc` can.

Usage: tailnet-forward.py <tailnet-host> <port> <local-port>
"""
import asyncio
import contextlib
import sys

HOST, PORT, LOCAL = sys.argv[1], sys.argv[2], int(sys.argv[3])


async def pump(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


async def handle(client_r, client_w):
    proc = await asyncio.create_subprocess_exec(
        "tailscale", "nc", HOST, PORT,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
    print(f"connection -> {HOST}:{PORT} (pid {proc.pid})", flush=True)
    await asyncio.gather(pump(client_r, proc.stdin), pump(proc.stdout, client_w),
                         return_exceptions=True)
    with contextlib.suppress(ProcessLookupError):  # tailscale nc may have exited already
        proc.kill()
    print(f"closed pid {proc.pid}", flush=True)


async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", LOCAL)
    print(f"listening on 127.0.0.1:{LOCAL} -> {HOST}:{PORT}", flush=True)
    await server.serve_forever()


asyncio.run(main())
