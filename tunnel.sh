#!/usr/bin/env bash
# Mantém o túnel serveo.net vivo com auto-reconexão automática.
# Uso: ./tunnel.sh
# O script imprime a URL pública assim que o túnel sobe.

PORT=${WEBHOOK_PORT:-8025}
INTERVAL=30   # keepalive SSH em segundos
RETRY_WAIT=5  # segundos antes de tentar reconectar

echo "Iniciando túnel serveo.net → localhost:$PORT"
echo "Ctrl+C para encerrar."
echo ""

while true; do
    ssh -R "80:localhost:$PORT" \
        -o ServerAliveInterval=$INTERVAL \
        -o ServerAliveCountMax=5 \
        -o ExitOnForwardFailure=yes \
        -o StrictHostKeyChecking=no \
        serveo.net

    echo ""
    echo "[$(date '+%H:%M:%S')] Túnel encerrado. Reconectando em ${RETRY_WAIT}s..."
    sleep $RETRY_WAIT
done
