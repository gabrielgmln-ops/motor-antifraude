# Dockerfile
# Imagem única usada pelos serviços "motor" (consumidor) e "api" (painel).
FROM python:3.12-slim

# Evita arquivos .pyc e garante logs imediatos no "docker compose logs"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copia primeiro só o necessário para instalar dependências (aproveita cache de camadas)
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Usuário sem privilégios: o processo não roda como root dentro do contêiner
RUN useradd --create-home motor
USER motor
