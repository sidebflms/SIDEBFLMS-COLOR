# SIDEBFLMS COLOR

Color asistido para DaVinci Resolve Studio. SIDEBFLMS, Madrid.

Tres nodos, porque es lo que la API de Resolve sabe hacer:

| Nodo | Dueño | Cómo se escribe |
|---|---|---|
| 1 · Normalización | Gestión de color del proyecto | La app **no** lo toca; verifica que exista y avisa si no |
| 2 · Balance, por clip | La app | `SetCDL()` — 10 números legibles y editables |
| 3 · Look, por proyecto | La app | `.cube` 33³ vía `SetLUT()` |

**Nada destructivo.** Antes de tocar un clip se crea la versión `SIDEB COLOR` y todo
se escribe ahí. El grado original queda intacto en su versión.

## Puesta en marcha

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python tests/media/generate.py   # material sintetico de prueba
.venv/bin/python -m pytest -q
```

## Documentos

- **[BITACORA.md](BITACORA.md)** — qué funciona, qué no, y qué hay que hacer. Empieza aquí.
- [CONTRATOS.md](CONTRATOS.md) — los tipos que cruzan módulos. Congelados.
- [PROPIEDAD.md](PROPIEDAD.md) — qué archivo es de quién.
- [CAPACIDADES.md](CAPACIDADES.md) — qué puede y qué no puede hacer la app, sin adornos.
