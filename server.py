"""
server.py — TCP server for Pi Zero client connections.
Each connected Pi Zero = one player in the engine.

Threading: background threads push work items to a queue; the main Tkinter
thread polls the queue via root.after() and executes engine calls.
"""

from __future__ import annotations

import base64
import json
import logging
import queue
import socket
import threading

from engine import StoryEngine, STATUS_ACTIVE, STATUS_ENCOUNTER, STATUS_GAME_OVER
from player_renderer import render_to_png_bytes

log = logging.getLogger(__name__)

MAX_PLAYERS = 20
PORT = 9999
POLL_INTERVAL_MS = 50  # how often main thread polls the queue


class _Client:
    __slots__ = ("conn", "addr", "player_id", "device_id", "screen_w", "screen_h")
    def __init__(self, conn: socket.socket, addr: tuple):
        self.conn = conn
        self.addr = addr
        self.player_id: str | None = None
        self.device_id: str | None = None
        self.screen_w = 480
        self.screen_h = 800


class GameServer:

    def __init__(self, engine: StoryEngine, tk_root,
                 port: int = PORT, host: str = "0.0.0.0"):
        self.engine = engine
        self.root = tk_root
        self.port = port
        self.host = host

        self._clients: dict[str, _Client] = {}   # player_id → _Client
        self._device_players: dict[str, str] = {}  # device_id → player_id (all day)
        self._lock = threading.Lock()
        self._server_sock: socket.socket | None = None
        self._running = False
        self._queue: queue.Queue = queue.Queue()
        self._poll_id = None

        # Hook into engine callbacks — these fire on the main thread
        # (from ControlWindow interactions), so it's safe to call
        # _send_render directly.
        orig_graph = self.engine.on_graph_change
        orig_encounter = self.engine.on_encounter_start

        def _on_graph_change(*a, **kw):
            if orig_graph:
                orig_graph(*a, **kw)
            if kw.get("canvas_only"):
                return
            moved_player = kw.get("moved_player")
            if moved_player:
                self.push_state(moved_player)
            else:
                self._push_all()

        def _on_encounter_start(*a, **kw):
            if orig_encounter:
                orig_encounter(*a, **kw)
            # All participants (fled + witness) need a fresh screen
            self._push_all()

        self.engine.on_graph_change = _on_graph_change
        self.engine.on_encounter_start = _on_encounter_start

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start accepting connections. Must be called from main thread."""
        self._running = True
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(5)
        self._server_sock.settimeout(1.0)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self._poll_id = self.root.after(POLL_INTERVAL_MS, self._poll_queue)
        log.info("Server listening on %s:%d", self.host, self.port)

    def stop(self):
        """Stop the server. Safe to call from any thread."""
        self._running = False
        if self._poll_id:
            try:
                self.root.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        with self._lock:
            for c in list(self._clients.values()):
                try:
                    c.conn.close()
                except Exception:
                    pass
            self._clients.clear()
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        log.info("Server stopped")

    def push_state(self, player_id: str):
        """Render and send state to one specific client. Main-thread safe."""
        with self._lock:
            client = self._clients.get(player_id)
            if client is None:
                return
        self._send_render(client)

    # ------------------------------------------------------------------
    # Internal: accept loop (background thread)
    # ------------------------------------------------------------------

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._server_sock.accept()
                log.info("Connection from %s", addr)
                threading.Thread(target=self._handle_client,
                                 args=(conn, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as exc:
                if self._running:
                    log.error("Accept error: %s", exc)

    # ------------------------------------------------------------------
    # Internal: per-client handler (background thread)
    # ------------------------------------------------------------------

    def _handle_client(self, conn: socket.socket, addr):
        conn.settimeout(None)
        buf = b""
        client = _Client(conn, addr)

        try:
            while self._running:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    self._handle_message(client, line)
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            self._queue.put(("disconnect", client))
            try:
                conn.close()
            except Exception:
                pass

    def _handle_message(self, client: _Client, raw: bytes):
        try:
            msg = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            log.warning("Bad JSON from %s: %s", client.addr, exc)
            return

        msg_type = msg.get("type")

        if msg_type == "hello":
            client.screen_w = msg.get("width", 480)
            client.screen_h = msg.get("height", 800)
            client.device_id = msg.get("device_id") or f"wall-{client.addr[0]}:{client.addr[1]}"
            self._queue.put(("spawn", client))

        elif msg_type == "choice":
            idx = msg.get("index")
            if idx is not None and client.player_id:
                self._queue.put(("choice", client.player_id, int(idx)))

    # ------------------------------------------------------------------
    # Internal: queue poll (main thread, via root.after)
    # ------------------------------------------------------------------

    def _poll_queue(self):
        if not self._running:
            return
        try:
            while True:
                item = self._queue.get_nowait()
                self._process_item(item)
        except queue.Empty:
            pass
        except Exception as exc:
            log.error("Queue processing error: %s", exc)
        self._poll_id = self.root.after(POLL_INTERVAL_MS, self._poll_queue)

    def _process_item(self, item):
        kind = item[0]
        if kind == "spawn":
            client = item[1]
            self._spawn_player(client)
        elif kind == "choice":
            _, pid, idx = item
            self.engine.make_choice(pid, idx)
        elif kind == "disconnect":
            client = item[1]
            self._on_disconnect(client)

    # ------------------------------------------------------------------
    # Internal: game logic (main thread)
    # ------------------------------------------------------------------

    def _spawn_player(self, client: _Client):
        device_id = client.device_id or f"wall-{client.addr[0]}:{client.addr[1]}"

        with self._lock:
            pid = self._device_players.get(device_id)
            if pid and pid in self.engine.players:
                stale = self._clients.get(pid)
                if stale is not client:
                    stale.player_id = None
                client.player_id = pid
                self._clients[pid] = client
            else:
                if len(self.engine.players) >= MAX_PLAYERS:
                    log.warning("Max players reached, rejecting %s", client.addr)
                    return
                state = self.engine.spawn_player()
                pid = state.player_id
                client.player_id = pid
                self._clients[pid] = client
                self._device_players[device_id] = pid

        log.info("Device %s -> player %s (%s)", device_id, pid, client.addr)
        self._send_render(client)

    def _on_disconnect(self, client: _Client):
        pid = client.player_id
        if pid is None:
            return
        with self._lock:
            if self._clients.get(pid) is client:
                self._clients.pop(pid, None)
        log.info("Player %s disconnected (wall idle — state kept)", pid)

    # ------------------------------------------------------------------
    # Internal: push state to client (any thread, but only called from
    #           main thread via _push_all / _spawn_player / _send_render)
    # ------------------------------------------------------------------

    def _send_render(self, client: _Client):
        pid = client.player_id
        if pid is None:
            return
        state = self.engine.players.get(pid)
        if state is None:
            return
        node = self.engine.active_graph.nodes.get(state.current_node)
        node_title = None
        if node and self.engine.world:
            wn = self.engine.world.nodes.get(state.current_node)
            if wn:
                node_title = wn.title or state.current_node.replace("_", " ")

        if state.status == STATUS_ENCOUNTER:
            scene_text = state.encounter_text or ""
            if not scene_text.strip():
                scene_text = "Someone else was here."
            else:
                scene_text = f"Someone else was here.\n\n{scene_text}"
            choices = []
            trace = ""
            use_restart = False
        else:
            scene_text = self.engine.get_display_text_for_player(pid)
            if not scene_text and node:
                scene_text = getattr(node, "text", "")
            choices = state.current_links or []
            trace = self.engine.get_player_trace_text(pid)
            use_restart = state.status == STATUS_GAME_OVER

        try:
            png = render_to_png_bytes(
                player_id=pid,
                scene_text=scene_text,
                choices=choices,
                trace=trace,
                status=state.status,
                node_id=state.current_node,
                node_title=node_title,
                screen_w=client.screen_w,
                screen_h=client.screen_h,
            )
        except Exception as exc:
            log.error("Render error for %s: %s", pid, exc)
            return

        msg = json.dumps({
            "player_id": pid,
            "status": state.status,
            "encounter": state.status == STATUS_ENCOUNTER,
            "image_b64": base64.b64encode(png).decode("ascii"),
            "choice_count": len(choices),
        })

        try:
            client.conn.sendall((msg + "\n").encode("utf-8"))
        except OSError as exc:
            log.warning("Send error to %s: %s", pid, exc)

    def _push_all(self):
        """Push updated state to all connected clients. Main-thread only."""
        with self._lock:
            clients = list(self._clients.values())
        for c in clients:
            self._send_render(c)
