"""V5.4 test guard: no live network in tests. Any outbound socket connect raises."""
import socket

import pytest

_real_connect = socket.socket.connect


def _guarded_connect(self, address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, str) and (host.startswith('127.') or host in ('localhost', '::1') or host.startswith('/')):
        return _real_connect(self, address, *args, **kwargs)
    raise OSError(f'Network disabled in tests (attempted {address!r})')


@pytest.fixture(autouse=True, scope='session')
def _no_network():
    socket.socket.connect = _guarded_connect
    yield
    socket.socket.connect = _real_connect
