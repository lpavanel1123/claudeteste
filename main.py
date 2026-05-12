import config
from webhook_server import create_app


def main():
    print("=" * 55)
    print("  Receptor de Email — Mailgun Webhook")
    print("=" * 55)
    print(f"  Endereço monitorado : {config.EMAIL_ADDRESS}")
    print(f"  Webhook local       : http://localhost:{config.WEBHOOK_PORT}/webhook")
    print(f"  Arquivo de saída    : {config.INBOX_FILE}")
    if not config.MAILGUN_SIGNING_KEY:
        print("  [aviso] MAILGUN_SIGNING_KEY não configurada — sem verificação de assinatura")
    print("=" * 55)
    print("  Aguardando emails... (Ctrl+C para encerrar)\n")

    app = create_app()
    app.run(host=config.WEBHOOK_HOST, port=config.WEBHOOK_PORT)


if __name__ == "__main__":
    main()
