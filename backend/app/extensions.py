"""Istanze condivise dei componenti Flask, create qui e inizializzate in
`create_app` per evitare import circolari tra i moduli dell'app.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO

socketio = SocketIO()
limiter = Limiter(key_func=get_remote_address)
