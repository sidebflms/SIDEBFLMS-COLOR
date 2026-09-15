# PROPIEDAD DE ARCHIVOS

**Dos agentes no editan nunca el mismo archivo.** Si crees que necesitas tocar algo
que no es tuyo, el diseño está mal: se lo dices al orquestador y se reparte de otra
forma. No lo edites «un momentito».

Crear archivos **nuevos dentro de tu carpeta** sí es tuyo, sin preguntar.

| Agente | Rama | Propiedad exclusiva |
|---|---|---|
| **Orquestador** | `main` | `pyproject.toml`, `.gitignore`, `.github/`, `README.md`, `CONTRATOS.md`, `PROPIEDAD.md`, `BITACORA.md`, `CAPACIDADES.md`, `core/__init__.py`, `core/paths.py`, **`core/contracts.py`**, `tests/media/generate.py`, `tests/conftest.py`, `tests/test_entregables.py` |
| **A · color** | `agente/a-color` | `core/color/**`, `tests/test_color_*.py` |
| **B · análisis** | `agente/b-analisis` | `core/analysis/**`, `tests/test_analysis_*.py` |
| **C · matching** | `agente/c-matching` | `core/matching/**`, `tests/test_matching_*.py` |
| **D · io** | `agente/d-io` | `core/io/**`, `tests/test_io_*.py` |
| **E · resolve** | `agente/e-resolve` | `core/resolve/**`, `probe/**`, `tests/test_resolve_*.py` |
| **F · reverse** | `agente/f-reverse` | `core/reverse/**`, `tests/test_reverse_*.py` |
| **G · revisor 1** | `agente/g-revision1` | `tests/revision/test_ola1_*.py`, `docs/revision-ola1.md` |
| **H · gui** | `agente/h-gui` | `gui/**`, `tests/test_gui_*.py`, `capturas/**` |
| **I · revisor 2** | `agente/i-revision2` | `tests/revision/test_ola23_*.py`, `tests/test_e2e_*.py`, `docs/revision-ola23.md` |

Cada agente deja además un **`NOTAS.md` en su propia carpeta** (`core/color/NOTAS.md`,
`gui/NOTAS.md`…): qué decidió, qué descartó y por qué. Es lo que permite que el
revisor discrepe con criterio en vez de limitarse a leer el código.

## Archivos calientes — leer antes de tocar

- **`core/contracts.py`**: sólo el orquestador. Es lo que evita que las siete ramas
  dejen de encajar.
- **`tests/media/generate.py`**: sólo el orquestador. Todo el mundo lo importa; si
  cambian los píxeles, cambian todos los tests a la vez.
- **`tests/conftest.py`**: sólo el orquestador. Si necesitas un fixture compartido,
  pídelo. Fixtures tuyos, en tu propio archivo de test.
