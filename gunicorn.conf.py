
import threading

def post_worker_init(worker):
    from app import run_bot

    bot_thread = threading.Thread(
        target=run_bot,
        name="telegram-bot",
        daemon=True
    )
    bot_thread.start()
