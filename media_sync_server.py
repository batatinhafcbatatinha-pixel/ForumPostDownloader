#!/usr/bin/env python3
"""Small local file index server for XenForoPostDownloader watched mode."""

from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


class FileIndex:
    def __init__(self, root: Path, index_path: Path):
        self.root = root.resolve()
        self.index_path = index_path.resolve()
        self.lock = threading.Lock()
        self.names: set[str] = set()
        self.ids: set[str] = set()

        print(f"[XFPD] Inicializando FileIndex")
        print(f"[XFPD] Pasta raiz: {self.root}")
        print(f"[XFPD] Arquivo de índice: {self.index_path}")

        self._load()
        self.refresh()

        print(
            f"[XFPD] Índice carregado: "
            f"{len(self.names)} nomes, {len(self.ids)} IDs"
        )

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

    def _load(self) -> None:
        try:
            print(f"[XFPD] Carregando índice: {self.index_path}")

            data = json.loads(
                self.index_path.read_text(encoding="utf-8")
            )

            self.names = {
                key
                for value in data.get("names", [])
                if value
                for key in self.name_keys(value)
            }

            self.ids = {
                str(value)
                for value in data.get("ids", [])
                if value
            }

            print(
                f"[XFPD] Índice carregado com sucesso: "
                f"{len(self.names)} nomes / {len(self.ids)} IDs"
            )

        except FileNotFoundError:
            print(
                f"[XFPD] Índice não encontrado. "
                f"Será criado: {self.index_path}"
            )
            self.names = set()
            self.ids = set()

        except (OSError, ValueError) as exc:
            print(
                f"[XFPD] ERRO ao carregar índice: {exc}"
            )
            self.names = set()
            self.ids = set()

    def _save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "names": sorted(self.names),
            "ids": sorted(self.ids),
        }

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
            f"{len(self.names)} nomes / {len(self.ids)} IDs"
        )

    def refresh(self) -> None:
        print(f"[XFPD] Verificando arquivos em: {self.root}")

        with self.lock:
            if not self.root.exists():
                print(
                    f"[XFPD] AVISO: pasta não existe: {self.root}"
                )
                return

            if not self.root.is_dir():
                print(
                    f"[XFPD] AVISO: caminho não é uma pasta: {self.root}"
                )
                return

            found = 0
            new_files = 0

            for path in self.root.rglob("*"):
                if path.is_file() and path.resolve() != self.index_path:
                    found += 1

                    file_keys = self.name_keys(path.name)

                    if file_keys and not file_keys.issubset(self.names):
                        self.names.update(file_keys)
                        new_files += 1

                        # print(
                        #     f"[XFPD] Arquivo encontrado: {path}"
                        # )

            print(
                f"[XFPD] Scan concluído: "
                f"{found} arquivos encontrados, "
                f"{new_files} novos no índice"
            )

    def check(self, items: list[dict]) -> list[dict]:
        print(
            f"[XFPD] CHECK recebido: {len(items)} itens"
        )

        self.refresh()

        result = []

        with self.lock:
            for item in items:
                index = item.get("index")
                identity = str(item.get("id", ""))

                names = {
                    key
                    for name in item.get("names", [])
                    if name
                    for key in self.name_keys(name)
                }

                matching_names = names & self.names
                matching_id = bool(
                    identity and identity in self.ids
                )

                exists = bool(matching_id or matching_names)

                result.append({
                    "index": index,
                    "exists": exists,
                })

                if exists:
                    print(
                        f"[XFPD] DUPLICADO encontrado "
                        f"(index={index}, id={identity!r}, "
                        f"nomes={list(names)!r})"
                    )

                    if matching_id:
                        print(
                            f"[XFPD]   -> ID já registrado: {identity}"
                        )

                    if matching_names:
                        print(
                            f"[XFPD]   -> Nome(s) encontrado(s): "
                            f"{list(matching_names)}"
                        )
                else:
                    print(
                        f"[XFPD] NÃO encontrado "
                        f"(index={index}, id={identity!r}, "
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

    def register(self, items: list[dict]) -> None:
        print(
            f"[XFPD] REGISTER recebido: {len(items)} itens"
        )

        added_ids = 0
        added_names = 0

        with self.lock:
            for item in items:
                identity = str(item.get("id", ""))

                if identity:
                    if identity not in self.ids:
                        added_ids += 1
                        print(
                            f"[XFPD] Registrando ID: {identity}"
                        )

                    self.ids.add(identity)

                for name in item.get("names", []):
                    for key in self.name_keys(name):
                        if key not in self.names:
                            added_names += 1
                            print(
                                f"[XFPD] Registrando nome: {key}"
                            )

                        self.names.add(key)

            self._save()

        print(
            f"[XFPD] REGISTER concluído: "
            f"{added_ids} IDs novos, "
            f"{added_names} nomes novos"
        )


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

        if route == "/check":
            items = payload.get("items", [])

            if not isinstance(items, list):
                print(
                    "[XFPD] AVISO: /check recebeu "
                    "items que não é uma lista"
                )
                items = []

            self.send_json(
                200,
                {
                    "ok": True,
                    "items": self.index.check(items)
                }
            )
            return

        if route == "/register":
            items = payload.get("items", [])

            if not isinstance(items, list):
                print(
                    "[XFPD] AVISO: /register recebeu "
                    "items que não é uma lista"
                )
                items = []

            self.index.register(items)

            self.send_json(
                200,
                {
                    "ok": True
                }
            )
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
    print("=" * 60)

    file_index = FileIndex(
        root,
        index_path
    )

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
