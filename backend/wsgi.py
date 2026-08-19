"""Entrypoint di produzione per Gunicorn (Render).

Flask-SocketIO in produzione richiede un worker asincrono. Il documento di
progetto (sezione 6.1) non specificava quale; `eventlet` era la scelta più
comune ma i suoi stessi maintainer lo segnalano come deprecato (agosto 2026),
quindi si usa `gevent`, l'alternativa raccomandata da Flask-SocketIO e
ancora mantenuta attivamente. Il monkey-patch va fatto prima di qualsiasi
altro import (richiesto da `requests`/`psycopg2`), quindi resta la
primissima riga eseguibile.
Comando di avvio: `gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 wsgi:app`.
"""
from gevent import monkey

monkey.patch_all()

from app import create_app  # noqa: E402

app = create_app()
