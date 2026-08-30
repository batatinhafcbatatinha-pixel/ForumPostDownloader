#!/usr/bin/env python3
"""Small local file index server for XenForoPostDownloader watched mode."""

from __future__ import annotations

import argparse
import time
from functools import partial
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, urlunparse


# Keep request-level diagnostics visible immediately in a redirected CMD.
print = partial(print, flush=True)


class FileIndex:
    # How long a "check" reservation survives if no matching /register
    # (or /release) ever arrives -- e.g. the client crashed or the
    # download failed silently. After this many seconds the slot is
    # freed again so it doesn't permanently block a legitimate retry.
    PENDING_TTL_SECONDS = 10 * 60

    # Minimum time between full directory rescans triggered by /check.
    # Walking a library with hundreds of thousands of files on every
    # single request is what was turning a few-millisecond dedupe
    # check into a multi-second one -- and that multi-second window is
    # exactly when two concurrent /check calls for the same new file
    # can both come back "not a duplicate".
    MIN_REFRESH_INTERVAL_SECONDS = 30

    def __init__(self, root: Path, index_path: Path):
        self.root = root.resolve()
        self.index_path = index_path.resolve()
        self.lock = threading.Lock()
        self.threads: dict[str, dict[str, set[str] | dict[str, float]]] = {}

        # In-flight reservations: keys that a /check call has just
        # handed out as "new" but that haven't been confirmed by
        # /register yet. Treated as duplicates by other concurrent
        # checks so two workers can never both claim the same file.
        self._last_refresh_by_thread: dict[str, float] = {}

        print(f"[XFPD] Inicializando FileIndex")
        print(f"[XFPD] Pasta raiz: {self.root}")
        print(f"[XFPD] Arquivo de índice: {self.index_path}")

        self._load()
        print(
            f"[XFPD] Índice carregado: "
            f"{len(self.threads)} threads"
        )

    @staticmethod
    def thread_key(value: str) -> str:
        """Normalize a client-supplied title to one safe child directory."""
        value = re.sub(r"[\x00-\x1f\x7f]", "", str(value or "").strip())
        value = re.sub(r'[<>:"/\\|?*]', "-", value)
        value = re.sub(r"\s+", " ", value).strip().rstrip(". ")
        if not value:
            return "_unknown-thread"
        if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", value):
            value = f"_{value}"
        return value[:180].rstrip(". ") or "_unknown-thread"

    def _state(self, thread_name: str) -> dict[str, set[str] | dict[str, float]]:
        key = self.thread_key(thread_name)
        state = self.threads.setdefault(
            key,
            {"names": set(), "ids": set(), "pending_names": {}, "pending_ids": {}},
        )
        return state

    def _thread_path(self, thread_name: str) -> Path:
        return self.root / self.thread_key(thread_name)

    @staticmethod
    def normalize(value: str) -> str:
        return (
            str(value or "")
            .strip()
            .replace("\\", "/")
            .rsplit("/", 1)[-1]
            .casefold()
        )

    @classmethod
    def name_keys(cls, value: str) -> set[str]:
        """Return normalized aliases used for duplicate matching.

        Example: "Cardi B #Jul 24, 2025 - WJsgGqIJe5J.mov"
        also yields "wjsggqije5j.mov" and "wjsggqije5j".
        """
        normalized = cls.normalize(value)

        if not normalized:
            return set()

        keys = {normalized}

        name_path = Path(normalized)
        stem = name_path.stem.strip()
        suffix = name_path.suffix

        if stem:
            keys.add(stem)

            # "file(1).jpg" should match "file.jpg".
            copyless_stem = re.sub(r"\(\d+\)$", "", stem).strip()

            if copyless_stem and copyless_stem != stem:
                keys.add(copyless_stem)

                if suffix:
                    keys.add(f"{copyless_stem}{suffix}")

            # "hash.md.jpg" should also match "hash.jpg".
            if stem.endswith(".md"):
                mdless_stem = stem[:-3].strip()

                if mdless_stem:
                    keys.add(mdless_stem)

                    if suffix:
                        keys.add(f"{mdless_stem}{suffix}")

            if " - " in stem:
                tail = stem.rsplit(" - ", 1)[-1].strip()

                if tail:
                    keys.add(tail)

                    if suffix:
                        keys.add(f"{tail}{suffix}")

        return {key for key in keys if key}

    @staticmethod
    def normalize_identity(value: str) -> str:
        """Strip volatile query-string parts (signed tokens, exp, etc.)
        out of an id before using it for dedup matching.

        IDs coming from XFPD are often "embed_url|direct_cdn_url",
        where the CDN half carries a fresh signed token (JWT / exp /
        signature) every time the client resolves the same piece of
        content again. Matching on the raw string means identical
        content can silently get a "new" id -- and a duplicate
        download -- purely because the token changed. Dropping the
        query string keeps the stable host+path (which is where the
        actual file slug lives) while ignoring the part that's
        guaranteed to churn.
        """
        value = str(value or "").strip()

        if not value:
            return ""

        parts = value.split("|")
        normalized_parts = []

        for part in parts:
            part = part.strip()

            if not part:
                continue

            try:
                parsed = urlparse(part)

                if parsed.scheme and parsed.netloc:
                    part = urlunparse(
                        (
                            parsed.scheme,
                            parsed.netloc,
                            parsed.path,
                            "",
                            "",
                            "",
                        )
                    )
            except ValueError:
                pass

            normalized_parts.append(part.casefold())

        return "|".join(normalized_parts)

    def _purge_pending(self, state: dict[str, set[str] | dict[str, float]]) -> None:
        """Drop reservations that were never confirmed by /register.

        Must be called with self.lock held.
        """
        cutoff = time.monotonic() - self.PENDING_TTL_SECONDS

        for store in (state["pending_names"], state["pending_ids"]):
            expired = [key for key, ts in store.items() if ts < cutoff]

            for key in expired:
                del store[key]

    def _load(self) -> None:
        try:
            print(f"[XFPD] Carregando índice: {self.index_path}")

            data = json.loads(
                self.index_path.read_text(encoding="utf-8")
            )

            self.threads = {}
            for thread_name, thread_data in data.get("threads", {}).items():
                if not isinstance(thread_data, dict):
                    continue
                state = self._state(thread_name)
                state["names"].update(
                    key for value in thread_data.get("names", []) if value for key in self.name_keys(value)
                )
                state["ids"].update(str(value) for value in thread_data.get("ids", []) if value)

            print(
                f"[XFPD] Índice carregado com sucesso: "
                f"{len(self.threads)} threads"
            )

        except FileNotFoundError:
            print(
                f"[XFPD] Índice não encontrado. "
                f"Será criado: {self.index_path}"
            )
            self.threads = {}

        except (OSError, ValueError) as exc:
            print(
                f"[XFPD] ERRO ao carregar índice: {exc}"
            )
            self.threads = {}

    def _save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {"threads": {key: {
            "names": sorted(state["names"]),
            "ids": sorted(state["ids"]),
        } for key, state in self.threads.items()}}

        temp_path = self.index_path.with_suffix(".tmp")

        temp_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        temp_path.replace(self.index_path)

        print(
            f"[XFPD] Índice salvo: "
            f"{len(self.threads)} threads"
        )

    def refresh(self, thread_name: str, force: bool = False) -> None:
        with self.lock:
            now = time.monotonic()

            thread_key = self.thread_key(thread_name)
            last_refresh = self._last_refresh_by_thread.get(thread_key, 0.0)
            if not force and (now - last_refresh) < self.MIN_REFRESH_INTERVAL_SECONDS:
                return

            self._last_refresh_by_thread[thread_key] = now

            thread_path = self._thread_path(thread_name)
            state = self._state(thread_name)
            names = state["names"]
            print(f"[XFPD] Verificando arquivos em: {thread_path}")

            if not thread_path.exists():
                print(
                    f"[XFPD] AVISO: pasta não existe: {thread_path}"
                )
                return

            if not thread_path.is_dir():
                print(
                    f"[XFPD] AVISO: caminho não é uma pasta: {thread_path}"
                )
                return

            found = 0
            new_files = 0

            for path in thread_path.rglob("*"):
                if path.is_file() and path.resolve() != self.index_path:
                    found += 1

                    if found % 25000 == 0:
                        print(
                            f"[XFPD] Scan em andamento: "
                            f"{found} arquivos verificados, "
                            f"{new_files} novos"
                        )

                    file_keys = self.name_keys(path.name)

                    if file_keys and not file_keys.issubset(names):
                        names.update(file_keys)
                        new_files += 1

                        # print(
                        #     f"[XFPD] Arquivo encontrado: {path}"
                        # )

            print(
                f"[XFPD] Scan concluído: "
                f"{found} arquivos encontrados, "
                f"{new_files} novos no índice"
            )

    def check(self, thread_name: str, items: list[dict]) -> list[dict]:
        print(
            f"[XFPD] CHECK recebido: {len(items)} itens na thread {self.thread_key(thread_name)!r}"
        )

        # No longer forces a full rglob scan on every call -- see
        # MIN_REFRESH_INTERVAL_SECONDS. This also shrinks the window
        # between "is it new?" and "claim it" below.
        self.refresh(thread_name)
        state = self._state(thread_name)
        names_index = state["names"]
        ids_index = state["ids"]
        pending_names = state["pending_names"]
        pending_ids = state["pending_ids"]

        result = []

        with self.lock:
            self._purge_pending(state)

            for item in items:
                index = item.get("index")
                raw_identity = str(item.get("id", ""))
                identity = self.normalize_identity(raw_identity)
                raw_names = item.get("names", [])

                if not isinstance(raw_names, list):
                    raw_names = []

                print(
                    f"[XFPD] CHECK item index={index} id={raw_identity!r} "
                    f"nomes_recebidos={raw_names!r}"
                )

                names = {
                    key
                    for name in raw_names
                    if name
                    for key in self.name_keys(name)
                }

                for raw_name in raw_names:
                    keys = sorted(self.name_keys(str(raw_name)))
                    exists_by_name = any(
                        key in names_index or key in pending_names
                        for key in keys
                    )

                    print(
                        f"[XFPD] CHECK nome: {raw_name!r} -> "
                        f"{'EXISTE' if exists_by_name else 'NAO_EXISTE'} "
                        f"(chaves={keys!r})"
                    )

                matching_names = (
                    (names & names_index) | (names & pending_names.keys())
                )
                matching_id = bool(
                    identity
                    and (identity in ids_index or identity in pending_ids)
                )

                print(
                    f"[XFPD] CHECK id: {raw_identity!r} -> "
                    f"{'EXISTE' if matching_id else 'NAO_EXISTE'}"
                )

                exists = bool(matching_id or matching_names)

                result.append({
                    "index": index,
                    "exists": exists,
                })

                if exists:
                    print(
                        f"[XFPD] DUPLICADO encontrado "
                        f"(index={index}, id={raw_identity!r}, "
                        f"nomes={list(names)!r})"
                    )

                    if matching_id:
                        print(
                            f"[XFPD]   -> ID já registrado: {raw_identity}"
                        )

                    if matching_names:
                        print(
                            f"[XFPD]   -> Nome(s) encontrado(s): "
                            f"{list(matching_names)}"
                        )
                else:
                    # Claim it immediately, before releasing the lock,
                    # so a second concurrent /check for this same item
                    # (another download worker racing this one) sees
                    # it as a duplicate instead of also downloading it.
                    # /register later just confirms/persists the claim.
                    now = time.monotonic()

                    if identity:
                        pending_ids[identity] = now

                    for key in names:
                        pending_names[key] = now

                    print(
                        f"[XFPD] NÃO encontrado -- reservado "
                        f"(index={index}, id={raw_identity!r}, "
                        f"nomes={list(names)!r})"
                    )

        duplicates = sum(
            1 for item in result if item["exists"]
        )

        print(
            f"[XFPD] CHECK concluído: "
            f"{duplicates}/{len(items)} duplicados"
        )

        return result

    def register(self, thread_name: str, items: list[dict]) -> None:
        print(
            f"[XFPD] REGISTER recebido: {len(items)} itens na thread {self.thread_key(thread_name)!r}"
        )

        added_ids = 0
        added_names = 0

        state = self._state(thread_name)
        names_index = state["names"]
        ids_index = state["ids"]
        pending_names = state["pending_names"]
        pending_ids = state["pending_ids"]

        with self.lock:
            for item in items:
                raw_identity = str(item.get("id", ""))
                identity = self.normalize_identity(raw_identity)
                raw_names = item.get("names", [])

                if not isinstance(raw_names, list):
                    raw_names = []

                print(
                    f"[XFPD] REGISTER item id={raw_identity!r} "
                    f"nomes_recebidos={raw_names!r}"
                )

                if identity:
                    if identity not in ids_index:
                        added_ids += 1
                        print(
                            f"[XFPD] Registrando ID: {raw_identity}"
                        )

                    ids_index.add(identity)
                    # Confirmed -- no longer just a reservation.
                    pending_ids.pop(identity, None)

                for name in raw_names:
                    keys = sorted(self.name_keys(str(name)))

                    print(
                        f"[XFPD] REGISTER nome: {name!r} -> "
                        f"chaves={keys!r}"
                    )

                    for key in keys:
                        if key not in names_index:
                            added_names += 1
                            print(
                                f"[XFPD] Registrando nome: {key}"
                            )

                        names_index.add(key)
                        pending_names.pop(key, None)

            self._save()

        print(
            f"[XFPD] REGISTER concluído: "
            f"{added_ids} IDs novos, "
            f"{added_names} nomes novos"
        )

    def release(self, thread_name: str, items: list[dict]) -> None:
        """Free reservations for items whose download failed.

        Optional: without this, a failed-and-never-registered item
        just sits as "pending" until PENDING_TTL_SECONDS elapses,
        which is a safe (if slightly slow) fallback on its own. Call
        this to free it immediately and allow an instant retry.
        """
        print(
            f"[XFPD] RELEASE recebido: {len(items)} itens"
        )

        state = self._state(thread_name)
        with self.lock:
            for item in items:
                identity = self.normalize_identity(
                    str(item.get("id", ""))
                )
                raw_names = item.get("names", [])

                if not isinstance(raw_names, list):
                    raw_names = []

                if identity:
                    state["pending_ids"].pop(identity, None)

                for name in raw_names:
                    for key in self.name_keys(str(name)):
                        state["pending_names"].pop(key, None)


class Handler(BaseHTTPRequestHandler):
    server_version = "XFPDMediaSync/1.0"

    @property
    def index(self) -> FileIndex:
        return self.server.file_index  # type: ignore[attr-defined]

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header(
            "Content-Length",
            str(len(body))
        )
        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS"
        )

        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            print(
                f"[XFPD] Cliente encerrou a conexão antes de receber "
                f"a resposta: {self.command} {self.path}"
            )

    def do_OPTIONS(self) -> None:  # noqa: N802
        print(
            f"[XFPD] OPTIONS {self.path} "
            f"de {self.client_address[0]}"
        )

        self.send_json(204, {})

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path

        print(
            f"[XFPD] GET {route} "
            f"de {self.client_address[0]}"
        )

        if route == "/health":
            print("[XFPD] Health check OK")
            self.send_json(200, {"ok": True})
        else:
            print(f"[XFPD] Rota GET desconhecida: {route}")
            self.send_json(
                404,
                {
                    "ok": False,
                    "error": "not_found"
                }
            )

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path

        print(
            f"[XFPD] POST {route} "
            f"de {self.client_address[0]}"
        )

        try:
            length = int(
                self.headers.get("Content-Length", "0")
            )

            raw_body = self.rfile.read(length)

            payload = json.loads(
                raw_body or b"{}"
            )

        except (ValueError, json.JSONDecodeError) as exc:
            print(
                f"[XFPD] ERRO ao processar JSON: {exc}"
            )

            self.send_json(
                400,
                {
                    "ok": False,
                    "error": "invalid_json"
                }
            )
            return

        print(
            f"[XFPD] Payload recebido em {route}: "
            f"tipo={type(payload).__name__}, "
            f"chaves={list(payload.keys()) if isinstance(payload, dict) else 'n/a'}"
        )

        if route == "/check":
            thread_name = payload.get("threadName", "")
            items = payload.get("items", [])

            if not isinstance(items, list):
                print(
                    "[XFPD] AVISO: /check recebeu "
                    "items que não é uma lista"
                )
                items = []

            try:
                checked_items = self.index.check(thread_name, items)
            except Exception as exc:
                print(
                    f"[XFPD] ERRO interno em /check: "
                    f"{type(exc).__name__}: {exc!r}"
                )
                self.send_json(
                    500,
                    {"ok": False, "error": "check_failed"}
                )
                return

            self.send_json(200, {"ok": True, "items": checked_items})
            return

        if route == "/register":
            thread_name = payload.get("threadName", "")
            items = payload.get("items", [])

            if not isinstance(items, list):
                print(
                    "[XFPD] AVISO: /register recebeu "
                    "items que não é uma lista"
                )
                items = []

            try:
                self.index.register(thread_name, items)
            except Exception as exc:
                print(
                    f"[XFPD] ERRO interno em /register: "
                    f"{type(exc).__name__}: {exc!r}"
                )
                self.send_json(
                    500,
                    {"ok": False, "error": "register_failed"}
                )
                return

            self.send_json(
                200,
                {
                    "ok": True
                }
            )
            return

        if route == "/release":
            thread_name = payload.get("threadName", "")
            items = payload.get("items", [])

            if not isinstance(items, list):
                print(
                    "[XFPD] AVISO: /release recebeu "
                    "items que não é uma lista"
                )
                items = []

            try:
                self.index.release(thread_name, items)
            except Exception as exc:
                print(
                    f"[XFPD] ERRO interno em /release: "
                    f"{type(exc).__name__}: {exc!r}"
                )
                self.send_json(
                    500,
                    {"ok": False, "error": "release_failed"}
                )
                return

            self.send_json(200, {"ok": True})
            return

        print(
            f"[XFPD] Rota POST desconhecida: {route}"
        )

        self.send_json(
            404,
            {
                "ok": False,
                "error": "not_found"
            }
        )

    def log_message(
        self,
        format: str,
        *args: object
    ) -> None:
        print(
            f"[XFPD] {self.address_string()} - "
            f"{format % args}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index downloaded media for XFPD watched mode"
    )

    parser.add_argument(
        "--root",
        required=True,
        help="Folder containing downloaded media"
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8765
    )

    parser.add_argument(
        "--index",
        default="",
        help="Optional persistent index JSON path"
    )

    args = parser.parse_args()

    root = Path(args.root).expanduser()

    index_path = (
        Path(args.index).expanduser()
        if args.index
        else root / ".xfpd-media-index.json"
    )

    print("=" * 60)
    print("[XFPD] Iniciando servidor")
    print("[XFPD] Logs detalhados de CHECK/REGISTER: habilitados")
    print("=" * 60)

    file_index = FileIndex(
        root,
        index_path
    )

    def periodic_refresh() -> None:
        while True:
            time.sleep(FileIndex.MIN_REFRESH_INTERVAL_SECONDS)
            for thread_name in list(file_index.threads):
                file_index.refresh(thread_name, force=True)

    refresh_thread = threading.Thread(
        target=periodic_refresh,
        daemon=True
    )
    refresh_thread.start()

    server = ThreadingHTTPServer(
        (args.host, args.port),
        Handler
    )

    server.file_index = file_index  # type: ignore[attr-defined]

    print()
    print("[XFPD] SERVIDOR ONLINE")
    print(f"[XFPD] Endereço: http://{args.host}:{args.port}")
    print(f"[XFPD] Pasta monitorada: {file_index.root}")
    print(f"[XFPD] Índice: {file_index.index_path}")
    print(f"[XFPD] Health: http://{args.host}:{args.port}/health")
    print()
    print("[XFPD] Aguardando requisições...")
    print("=" * 60)

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print()
        print("[XFPD] Ctrl+C recebido.")
        print("[XFPD] Parando servidor...")

    finally:
        server.server_close()
        print("[XFPD] Servidor encerrado.")


if __name__ == "__main__":
    main()