"""SIS-003 laboratory: SQLite hash chain with an authenticated checkpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import tempfile
from pathlib import Path


ZERO_HASH = "0" * 64


class IntegrityError(RuntimeError):
    """Stored evidence or its authenticated checkpoint cannot be trusted."""


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class AnchorLedger:
    """
    Experimental ledger.

    The database, checkpoint and key are separate files, but may still share
    one security domain. This is not protection against full host compromise.
    """

    def __init__(
        self,
        database: str | Path,
        checkpoint: str | Path,
        key_file: str | Path,
    ):
        self.database = Path(database)
        self.checkpoint = Path(checkpoint)
        self.key_file = Path(key_file)

        paths = (self.database, self.checkpoint, self.key_file)
        existed = tuple(p.exists() for p in paths)

        if any(existed) and not all(existed):
            raise IntegrityError(
                "Incomplete ledger state: refusing implicit reinitialization"
            )

        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)

        if not any(existed):
            self._create_key_exclusive()

        self.key = self.key_file.read_bytes()
        if len(self.key) != 32:
            raise IntegrityError("Invalid checkpoint authentication key")

        if not any(existed):
            self.db = sqlite3.connect(str(self.database))
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("""
                CREATE TABLE evidence (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL
                )
            """)
            self.db.commit()
            self._write_checkpoint(0, ZERO_HASH)
        else:
            self.db = sqlite3.connect(str(self.database))
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA synchronous=FULL")
        if len(self.key) != 32:
            self.db.close()
            raise IntegrityError("Invalid checkpoint authentication key")

        self.verify_or_raise()

    def _create_key_exclusive(self) -> None:
        # Exclusive creation prevents accidental overwriting of an existing key.
        fd = os.open(
            str(self.key_file),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(secrets.token_bytes(32))
            stream.flush()
            os.fsync(stream.fileno())

    def _checkpoint_payload(self, sequence: int, last_hash: str) -> dict:
        return {
            "version": 1,
            "sequence": sequence,
            "last_hash": last_hash,
        }

    def _mac(self, payload: dict) -> str:
        return hmac.new(
            self.key, canonical(payload), hashlib.sha256
        ).hexdigest()

    def _write_checkpoint(self, sequence: int, last_hash: str) -> None:
        payload = self._checkpoint_payload(sequence, last_hash)
        document = {**payload, "mac": self._mac(payload)}
        self._atomic_write(self.checkpoint, canonical(document) + b"\n")

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)

            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _read_checkpoint(self) -> dict:
        try:
            document = json.loads(self.checkpoint.read_text("utf-8"))
            payload = {
                "version": document["version"],
                "sequence": document["sequence"],
                "last_hash": document["last_hash"],
            }
            supplied_mac = document["mac"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise IntegrityError("Checkpoint is missing or malformed") from exc

        if payload["version"] != 1:
            raise IntegrityError("Unsupported checkpoint version")

        if not isinstance(payload["sequence"], int) or payload["sequence"] < 0:
            raise IntegrityError("Invalid checkpoint sequence")

        if not hmac.compare_digest(self._mac(payload), str(supplied_mac)):
            raise IntegrityError("Checkpoint authentication failed")

        return payload

    @staticmethod
    def _record_hash(sequence: int, event_id: str, summary: str,
                     previous_hash: str) -> str:
        return digest({
            "sequence": sequence,
            "event_id": event_id,
            "summary": summary,
            "previous_hash": previous_hash,
        })

    def verify(self) -> tuple[bool, int]:
        try:
            checkpoint = self._read_checkpoint()
            previous = ZERO_HASH
            count = 0

            rows = self.db.execute(
                "SELECT * FROM evidence ORDER BY sequence"
            ).fetchall()

            for row in rows:
                record = dict(row)
                expected_sequence = count + 1

                if record["sequence"] != expected_sequence:
                    return False, count
                if record["previous_hash"] != previous:
                    return False, count

                expected_hash = self._record_hash(
                    record["sequence"],
                    record["event_id"],
                    record["summary"],
                    previous,
                )
                if not hmac.compare_digest(
                    expected_hash, record["record_hash"]
                ):
                    return False, count

                previous = expected_hash
                count += 1

            if checkpoint["sequence"] != count:
                return False, count
            if checkpoint["last_hash"] != previous:
                return False, count

            return True, count
        except (sqlite3.Error, IntegrityError, TypeError, ValueError):
            return False, 0

    def verify_or_raise(self) -> int:
        valid, count = self.verify()
        if not valid:
            raise IntegrityError("Ledger/checkpoint integrity verification failed")
        return count

    def append(self, event_id: str, summary: str) -> str:
        event_id = str(event_id).strip()
        summary = str(summary).strip()

        if not event_id or not summary:
            raise ValueError("event_id and summary are required")

        self.verify_or_raise()

        existing = self.db.execute(
            "SELECT * FROM evidence WHERE event_id = ?", (event_id,)
        ).fetchone()
        if existing:
            if existing["summary"] != summary:
                raise ValueError("Conflicting event redelivery")
            return existing["record_hash"]

        last = self.db.execute(
            "SELECT sequence, record_hash FROM evidence "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()

        sequence = (last["sequence"] + 1) if last else 1
        previous = last["record_hash"] if last else ZERO_HASH
        record_hash = self._record_hash(
            sequence, event_id, summary, previous
        )

        try:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute(
                "INSERT INTO evidence "
                "(sequence, event_id, summary, previous_hash, record_hash) "
                "VALUES (?, ?, ?, ?, ?)",
                (sequence, event_id, summary, previous, record_hash),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        # Deliberately fail closed if checkpoint update fails after DB commit.
        # Recovery must not silently invent a new trusted checkpoint.
        self._write_checkpoint(sequence, record_hash)
        self.verify_or_raise()
        return record_hash

    def close(self) -> None:
        self.db.close()
