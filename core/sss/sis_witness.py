"""SIS-006: persistent witness state machine.

Experimental local witness. This is not an independent remote trust anchor.
Initialization is explicit; existing incomplete stores fail closed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


ZERO_HASH = "0" * 64


class WitnessError(RuntimeError):
    """The witness state is missing, corrupt, or violates its protocol."""


@dataclass(frozen=True)
class Anchor:
    sequence: int
    last_hash: str


class PersistentWitness:
    """Persistent single-writer witness with explicit initialization."""

    _SCHEMA_VERSION = 1

    def __init__(self, database: str | Path):
        self.path = Path(database)

        if not self.path.is_file():
            raise WitnessError(
                "Witness database is missing; initialize it explicitly"
            )

        try:
            self.db = sqlite3.connect(
                str(self.path), timeout=10, isolation_level=None
            )
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self._validate_store()
        except Exception as exc:
            if hasattr(self, "db"):
                self.db.close()
            if isinstance(exc, WitnessError):
                raise
            raise WitnessError("Cannot open or validate witness store") from exc

    @classmethod
    def initialize(cls, database: str | Path) -> "PersistentWitness":
        """Create a new trusted zero-state store; never overwrite an existing path."""
        path = Path(database)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Exclusive file creation prevents accidental replacement of an
        # existing database, including an empty or damaged one.
        try:
            fd = __import__("os").open(
                str(path),
                __import__("os").O_CREAT
                | __import__("os").O_EXCL
                | __import__("os").O_WRONLY,
                0o600,
            )
            __import__("os").close(fd)
        except FileExistsError as exc:
            raise WitnessError(
                "Witness path already exists; refusing reinitialization"
            ) from exc
        except OSError as exc:
            raise WitnessError("Cannot create witness database") from exc

        db = None
        try:
            db = sqlite3.connect(str(path), timeout=10)
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA journal_mode=DELETE")
            db.executescript("""
                CREATE TABLE witness_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    schema_version INTEGER NOT NULL
                );

                CREATE TABLE witness_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    sequence INTEGER NOT NULL,
                    last_hash TEXT NOT NULL
                );

                CREATE TABLE witness_pending (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    expected_sequence INTEGER NOT NULL,
                    expected_hash TEXT NOT NULL,
                    candidate_sequence INTEGER NOT NULL,
                    candidate_hash TEXT NOT NULL
                );
            """)
            db.execute(
                "INSERT INTO witness_meta VALUES (1, ?)",
                (cls._SCHEMA_VERSION,),
            )
            db.execute(
                "INSERT INTO witness_state VALUES (1, 0, ?)",
                (ZERO_HASH,),
            )
            db.commit()
            db.close()
            db = None
            return cls(path)
        except Exception as exc:
            if db is not None:
                db.close()
            # Do not remove the failed file: its presence must not silently
            # turn a failed initialization into a fresh trusted state.
            raise WitnessError("Witness initialization failed; store retained") from exc

    @staticmethod
    def _validate(anchor: Anchor) -> None:
        if not isinstance(anchor, Anchor):
            raise WitnessError("Expected an Anchor")
        if (
            not isinstance(anchor.sequence, int)
            or isinstance(anchor.sequence, bool)
            or anchor.sequence < 0
        ):
            raise WitnessError("Invalid sequence")
        if (
            not isinstance(anchor.last_hash, str)
            or len(anchor.last_hash) != 64
            or any(c not in "0123456789abcdef" for c in anchor.last_hash)
        ):
            raise WitnessError("Invalid SHA-256 hash")
        if anchor.sequence == 0 and anchor.last_hash != ZERO_HASH:
            raise WitnessError("Sequence zero must use ZERO_HASH")
        if anchor.sequence > 0 and anchor.last_hash == ZERO_HASH:
            raise WitnessError("Nonzero sequence cannot use ZERO_HASH")

    def _validate_store(self) -> None:
        try:
            integrity = self.db.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise WitnessError("SQLite integrity check failed")

            meta = self.db.execute(
                "SELECT schema_version FROM witness_meta WHERE id=1"
            ).fetchone()
            state = self.db.execute(
                "SELECT sequence, last_hash FROM witness_state WHERE id=1"
            ).fetchone()

            if meta is None or state is None:
                raise WitnessError("Witness state is incomplete")
            if meta["schema_version"] != self._SCHEMA_VERSION:
                raise WitnessError("Unsupported witness schema version")

            self._validate(Anchor(state["sequence"], state["last_hash"]))

            state_rows = self.db.execute(
                "SELECT COUNT(*) FROM witness_state"
            ).fetchone()[0]
            pending_rows = self.db.execute(
                "SELECT COUNT(*) FROM witness_pending"
            ).fetchone()[0]
            if state_rows != 1 or pending_rows > 1:
                raise WitnessError("Unexpected witness row count")

            pending = self.db.execute(
                "SELECT * FROM witness_pending WHERE id=1"
            ).fetchone()
            if pending is not None:
                expected = Anchor(
                    pending["expected_sequence"], pending["expected_hash"]
                )
                candidate = Anchor(
                    pending["candidate_sequence"], pending["candidate_hash"]
                )
                self._validate(expected)
                self._validate(candidate)
                if candidate.sequence != expected.sequence + 1:
                    raise WitnessError("Invalid pending sequence transition")
                if candidate.last_hash == expected.last_hash:
                    raise WitnessError("Pending anchor does not change hash")
                if expected != Anchor(state["sequence"], state["last_hash"]):
                    raise WitnessError("Pending operation has stale expected state")
        except sqlite3.Error as exc:
            raise WitnessError("Cannot validate witness schema or state") from exc

    @property
    def current(self) -> Anchor:
        row = self.db.execute(
            "SELECT sequence, last_hash FROM witness_state WHERE id=1"
        ).fetchone()
        if row is None:
            raise WitnessError("Witness state is missing")
        result = Anchor(row["sequence"], row["last_hash"])
        self._validate(result)
        return result

    @property
    def pending(self) -> tuple[Anchor, Anchor] | None:
        row = self.db.execute(
            "SELECT * FROM witness_pending WHERE id=1"
        ).fetchone()
        if row is None:
            return None
        return (
            Anchor(row["expected_sequence"], row["expected_hash"]),
            Anchor(row["candidate_sequence"], row["candidate_hash"]),
        )

    def prepare(self, expected: Anchor, candidate: Anchor) -> str:
        self._validate(expected)
        self._validate(candidate)

        self.db.execute("BEGIN IMMEDIATE")
        try:
            current = self.current
            pending = self.pending

            if pending is not None:
                if pending == (expected, candidate):
                    self.db.execute("COMMIT")
                    return "PREPARE_IDEMPOTENT"
                raise WitnessError("Conflicting pending operation")

            if expected != current:
                raise WitnessError("Stale or mismatched expected anchor")
            if candidate.sequence != current.sequence + 1:
                raise WitnessError("Sequence must advance by exactly one")
            if candidate.last_hash == current.last_hash:
                raise WitnessError("New anchor must change the hash")

            self.db.execute(
                "INSERT INTO witness_pending VALUES (1, ?, ?, ?, ?)",
                (
                    expected.sequence,
                    expected.last_hash,
                    candidate.sequence,
                    candidate.last_hash,
                ),
            )
            self.db.execute("COMMIT")
            return "PREPARED"
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def commit(self, candidate: Anchor) -> str:
        self._validate(candidate)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current = self.current
            pending = self.pending

            if pending is None:
                if candidate == current:
                    self.db.execute("COMMIT")
                    return "COMMIT_IDEMPOTENT"
                raise WitnessError("No matching prepared operation")

            expected, prepared = pending
            if candidate != prepared or expected != current:
                raise WitnessError("Commit does not match prepared operation")

            self.db.execute(
                "UPDATE witness_state SET sequence=?, last_hash=? WHERE id=1",
                (prepared.sequence, prepared.last_hash),
            )
            self.db.execute("DELETE FROM witness_pending WHERE id=1")
            self.db.execute("COMMIT")
            return "COMMITTED"
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def compare_local(self, local: Anchor) -> str:
        self._validate(local)
        current = self.current
        if local.sequence < current.sequence:
            return "LOCAL_BEHIND"
        if local.sequence > current.sequence:
            return "LOCAL_AHEAD_UNCONFIRMED"
        if local.last_hash != current.last_hash:
            return "FORK_OR_REWRITE"
        return "MATCH"

    def close(self) -> None:
        self.db.close()
