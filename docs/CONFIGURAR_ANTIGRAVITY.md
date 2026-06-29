# Conectar el MCP de la tienda a Antigravity

Esta guía te lleva de "Antigravity está instalado" a "Antigravity ve y puede
usar las 9 tools del MCP de la tienda" en 5 pasos.

## Pre-flight check

Antes de tocar Antigravity, confirma que el servidor MCP arranca solo:

```powershell
cd C:\Users\medin\Downloads\Corpus\tienda-mcp
$env:PYTHONIOENCODING = 'utf-8'
py -m scripts.test_stdio_client
```

Debes ver `[OK] Conexion STDIO valida.` al final. Si no lo ves, **arregla
primero eso** — Antigravity no podrá hacer más que tu cliente local.

## Datos exactos para tu PC

| Campo | Valor (cópialo tal cual) |
|---|---|
| `command` | `C:\Users\medin\AppData\Local\Programs\Python\Python314\python.exe` |
| `args` | `["-m", "server.mcp_server"]` |
| `cwd` | `C:\Users\medin\Downloads\Corpus\tienda-mcp` |
| `env.PYTHONIOENCODING` | `utf-8` |

> Usamos la ruta absoluta de `python.exe` (no `py`) porque algunos clientes
> MCP no manejan bien el launcher con argumentos `-m`.

El template ya generado está en [mcp.config.json](../mcp.config.json) en la
raíz del proyecto.

## Pasos en Antigravity

### Opción A — desde la UI (recomendada)

1. **Abrir Antigravity**.
2. Abrir la paleta de comandos con `Ctrl+Shift+P`.
3. Buscar uno de estos comandos (Antigravity los nombra ligeramente
   distinto entre versiones — prueba en este orden):
   - `MCP: Add Server`
   - `Open MCP Settings`
   - `Settings: Configure MCP Servers`
   - `Preferences: Open User Settings (JSON)`
4. Cuando se abra el editor JSON, pega **dentro** del objeto `mcpServers`
   este bloque:

```json
"tienda-virtual": {
  "command": "C:\\Users\\medin\\AppData\\Local\\Programs\\Python\\Python314\\python.exe",
  "args": ["-m", "server.mcp_server"],
  "cwd": "C:\\Users\\medin\\Downloads\\Corpus\\tienda-mcp",
  "env": { "PYTHONIOENCODING": "utf-8" }
}
```

Si el archivo está vacío, pega el contenido completo de
[mcp.config.json](../mcp.config.json).

5. Guarda el archivo (`Ctrl+S`).
6. **Recarga la ventana**: `Ctrl+Shift+P` → `Developer: Reload Window`.

### Opción B — si Antigravity expone un panel de MCP

Algunas versiones de Antigravity tienen un panel lateral con un icono de
"plugins" o "extensions/MCP". Si lo ves:

1. Clic en el icono de MCP.
2. Botón "Add server" / "+".
3. Llenar el formulario con los datos de la tabla de arriba.
4. Guardar y recargar.

## Verificar que Antigravity ve las tools

Tras recargar:

1. Abre un nuevo chat en Antigravity.
2. Escribe: **"¿Qué tools tienes disponibles del servidor tienda-virtual?"**
   - Debería listar las 9: `buscar_productos`, `obtener_producto`,
     `verificar_inventario`, `agregar_al_carrito`, `ver_carrito`,
     `vaciar_carrito`, `crear_pedido`, `procesar_pago`, `consultar_pedido`.
3. Prueba una invocación natural:
   - **"Búscame laptops de menos de 4000 soles"** → debería llamar
     `buscar_productos` con `categoria="laptops"` y `precio_max=4000`,
     y devolver al menos P001.

## Si Antigravity no detecta el servidor

Causas típicas en orden de probabilidad:

1. **Rutas con `\` simple en JSON** → en JSON las contra-barras se
   escapan: `"C:\\Users\\..."`, no `"C:\Users\..."`.
2. **No recargaste la ventana** tras guardar. `Ctrl+Shift+P` → Reload
   Window.
3. **Otro proceso Python tomó la ruta** → cierra Antigravity completo,
   relánzalo desde cero.
4. **Permisos** → ejecuta Antigravity como administrador la primera vez.
5. **Logs**: revisa el output panel de Antigravity (`Ctrl+Shift+U`) y
   filtra por `mcp`. Cualquier traceback de Python aparecerá ahí.

## Plan B: usar el MCP desde Claude Desktop

Si quieres comparar comportamientos, el mismo `mcp.config.json` sirve para
Claude Desktop. La ruta del archivo es:

```
C:\Users\medin\AppData\Roaming\Claude\claude_desktop_config.json
```

Pega ahí el contenido de [mcp.config.json](../mcp.config.json) y reinicia
Claude Desktop. Es útil para tu demo: si Antigravity falla en vivo, abres
Claude Desktop y muestras lo mismo.
