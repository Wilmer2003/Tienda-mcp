"""
test_stdio_client.py
====================
Prueba de conexion real via STDIO contra el servidor MCP de la tienda.

Replica lo que hara Antigravity:
  1) lanza `python -m server.mcp_server` como subprocess,
  2) hace handshake MCP por stdin/stdout,
  3) lista las tools,
  4) llama una tool,
  5) cierra el subprocess limpiamente.

Si este script termina con OK, el servidor esta listo para Antigravity.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


CWD = str(Path(__file__).resolve().parent.parent)


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "server.mcp_server"],
        cwd=CWD,
        env=None,
    )

    print(f"[1/5] Lanzando servidor MCP desde subprocess:")
    print(f"      command = {params.command}")
    print(f"      args    = {params.args}")
    print(f"      cwd     = {params.cwd}")

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            print("[2/5] Handshake MCP (initialize) ...")
            await session.initialize()
            print("      OK")

            print("[3/5] Listando tools del servidor ...")
            tools = await session.list_tools()
            nombres = [t.name for t in tools.tools]
            print(f"      OK -- {len(nombres)} tools encontradas:")
            for n in nombres:
                print(f"        - {n}")

            print("[4/5] Llamando tool 'buscar_productos' "
                  "(categoria='laptops', precio_max=4000) ...")
            r = await session.call_tool(
                "buscar_productos",
                arguments={"query": "", "categoria": "laptops",
                           "precio_max": 4000},
            )
            # r.structuredContent o r.content
            n_resultados = 0
            if r.structuredContent:
                lst = r.structuredContent.get("result") \
                    if isinstance(r.structuredContent, dict) else None
                if isinstance(lst, list):
                    n_resultados = len(lst)
                    print(f"      OK -- {n_resultados} producto(s)")
                    for p in lst:
                        print(f"        {p.get('id')} {p.get('nombre')} "
                              f"S/ {p.get('precio')}")
            if n_resultados == 0:
                print(f"      (sin structuredContent, "
                      f"content len={len(r.content)})")

            print("[5/5] Cerrando subprocess MCP ...")

    print("\n[OK] Conexion STDIO valida. Antigravity puede usar este "
          "servidor con la misma configuracion.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
