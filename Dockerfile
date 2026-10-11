# Imagen del prototipo para publicarlo en internet (Render). Solo datos ficticios.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Primero las dependencias (se reutilizan entre despliegues si no cambian).
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY data ./data
# Instalación editable: el código busca `data/` junto al repositorio.
RUN pip install -e ".[ia]"

# Los casos y la cadena de evidencia viven en un disco persistente montado en /app/datos.
EXPOSE 10000
CMD python -m privacidad.canal servir --demo \
    --datos /app/datos/casos \
    --host 0.0.0.0 \
    --puerto "${PORT:-10000}" \
    --base-url "${RENDER_EXTERNAL_URL:-http://localhost:10000}" \
    --detras-de-proxy
