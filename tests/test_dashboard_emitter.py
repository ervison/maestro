import threading

from maestro.dashboard.emitter import DashboardEmitter


def test_emit_delivers_to_subscriber():
    emitter = DashboardEmitter()
    received = []

    def handler(event):
        received.append(event)

    emitter.subscribe(handler)
    emitter.emit({"type": "node_update", "id": "t1", "status": "active"})

    assert len(received) == 1
    assert received[0]["type"] == "node_update"
    assert received[0]["id"] == "t1"


def test_emit_delivers_to_multiple_subscribers():
    emitter = DashboardEmitter()
    received_a = []
    received_b = []

    emitter.subscribe(lambda e: received_a.append(e))
    emitter.subscribe(lambda e: received_b.append(e))
    emitter.emit({"type": "dag_ready", "tasks": []})

    assert len(received_a) == 1
    assert len(received_b) == 1


def test_unsubscribe_stops_delivery():
    emitter = DashboardEmitter()
    received = []
    handler = lambda e: received.append(e)

    emitter.subscribe(handler)
    emitter.unsubscribe(handler)
    emitter.emit({"type": "node_update", "id": "t1", "status": "done"})

    assert len(received) == 0


def test_emit_is_thread_safe():
    emitter = DashboardEmitter()
    received = []
    lock = threading.Lock()

    def handler(event):
        with lock:
            received.append(event)

    emitter.subscribe(handler)

    threads = [
        threading.Thread(
            target=emitter.emit,
            args=({"type": "node_log", "id": f"t{i}", "kind": "text", "text": "x"},),
        )
        for i in range(50)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(received) == 50


def test_emit_without_subscribers_does_not_raise():
    emitter = DashboardEmitter()

    emitter.emit({"type": "dag_ready", "tasks": []})
