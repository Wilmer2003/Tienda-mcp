"""
verificar_config_antigravity.py
================================
Lee `mcp.config.json` (la misma config que Antigravity usara) y valida
end-to-end que:
  - el python.exe que figura como 'command' existe,
  - el cwd existe,
  - el handshake MCP funciona,
  - las 9 tools se listan,
  - una llamada a tool retorna datos validos.

Si este script termina con [OK], Antigravity con la misma config funcionara.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "mcp.config.json"


async def main() -> int:
    print(f"[1/6] Leyendo {CONFIG_PATH} ...")
    if not CONFIG_PATH.exists():
        print("      FAIL: no existe mcp.config.json en la raiz del proyecto.")
        return 1
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    server = config.get("mcpServers", {}).get("tienda-virtual")
    if not server:
        print("      FAIL: falta el server 'tienda-virtual' en mcp.config.json.")
        return 1
    command = server["command"]
    args = server["args"]
    cwd = server.get("cwd", str(ROOT))
    env_override = server.get("env", {})
    print(f"      command = {command}")
    print(f"      args    = {args}")
    print(f"      cwd     = {cwd}")
    print(f"      env     = {env_override}")

    print("[2/6] Validando que el python.exe exista ...")
    if not Path(command).exists():
        print(f"      FAIL: no existe {command}.")
        print(f"      Sugerencia: ajusta 'command' en mcp.config.json al "
              f"python.exe correcto.")
        return 1
    print("      OK")

    print("[3/6] Validando que el cwd exista ...")
    if not Path(cwd).is_dir():
        print(f"      FAIL: no es directorio: {cwd}.")
        return 1
    print("      OK")

    # Construir env combinado: el del sistema + overrides de la config.
    env = {**os.environ, **env_override}

    params = StdioServerParameters(
        command=command, args=args, cwd=cwd, env=env,
    )

    print("[4/6] Arrancando subprocess MCP con la config exacta ...")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("      OK -- handshake completo")

            print("[5/6] Listando tools ...")
            tools = await session.list_tools()
            nombres = [t.name for t in tools.tools]
            print(f"      OK -- {len(nombres)} tools")
            esperados = {"buscar_productos", "obtener_producto",
                         "verificar_inventario", "agregar_al_carrito",
                         "ver_carrito", "vaciar_carrito",
                         "crear_pedido", "procesar_pago",
                         "consultar_pedido"}
            faltan = esperados - set(nombres)
            if faltan:
                print(f"      FAIL: faltan {faltan}")
                return 1

            print("[6/6] Probando call_tool('verificar_inventario', P001) ...")
            r = await session.call_tool("verificar_inventario",
                                        arguments={"producto_id": "P001"})
            datos = r.structuredContent or {}
            # FastMCP envuelve listas en {"result": [...]} y modelos
            # Pydantic los serializa al ras. Aceptamos ambos.
            payload = datos.get("result", datos) if isinstance(datos, dict) else datos
            info = payload.get("datos") if isinstance(payload, dict) else None
            if isinstance(info, dict) and "stock" in info:
                print(f"      OK -- P001 stock = {info['stock']}")
            else:
                print(f"      FAIL: respuesta inesperada {datos}")
                return 1

    print()
    print("=" * 60)
    print("[OK] mcp.config.json valido. Pega ese mismo JSON en Antigravity.")
    print("     Lee docs/CONFIGURAR_ANTIGRAVITY.md para los pasos exactos.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
