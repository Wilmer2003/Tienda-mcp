"""Comprueba que metodos publicos expone FastMCP para llamar tools in-process."""
import asyncio
from server.mcp_server import mcp


async def main():
    print("Atributos relevantes de FastMCP:")
    for attr in sorted(dir(mcp)):
        if attr.startswith("_") or attr.startswith("get_"):
            continue
        if "tool" in attr.lower() or "call" in attr.lower():
            print(f"  {attr}")

    print()
    print("Probando mcp.call_tool('buscar_productos', {'query': 'laptop'}):")
    try:
        out = await mcp.call_tool("buscar_productos", {"query": "laptop"})
        print(f"  OK -> {type(out).__name__}")
        if isinstance(out, tuple):
            for i, x in enumerate(out):
                print(f"     [{i}] {type(x).__name__} :: {repr(x)[:150]}")
        else:
            print(f"     {repr(out)[:300]}")
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
