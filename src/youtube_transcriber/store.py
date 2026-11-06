from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, video_id TEXT NOT NULL, language TEXT NOT NULL,
                status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                transcript TEXT, error TEXT, kind TEXT NOT NULL DEFAULT 'caption', input_path TEXT)''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'kind' not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'caption'")
                db.execute('ALTER TABLE jobs ADD COLUMN input_path TEXT')
            if 'owner_id' not in columns:
                db.execute('ALTER TABLE jobs ADD COLUMN owner_id TEXT')
            db.execute('CREATE INDEX IF NOT EXISTS job_owner_lookup ON jobs(owner_id, video_id, language, status)')
            db.execute('CREATE INDEX IF NOT EXISTS job_lookup ON jobs(video_id, language, status)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='queued' WHERE status='processing'")
            terminal = db.execute("SELECT input_path FROM jobs WHERE kind='audio' AND status IN ('completed','failed')").fetchall()
        for row in terminal:
            Path(row['input_path']).unlink(missing_ok=True)

    def create(self, video_id, language, owner_id=None):
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT id FROM jobs WHERE owner_id IS ? AND video_id=? AND language=? AND (status IN ('queued','processing') OR (status='completed' AND updated>?)) ORDER BY created DESC LIMIT 1", (owner_id, video_id, language, now - 86400)).fetchone()
            if row:
                return row['id']
            id = uuid4().hex
            db.execute('INSERT INTO jobs (id, video_id, language, status, created, updated, owner_id, transcript, error) VALUES (?,?,?,?,?,?,?,NULL,NULL)', (id, video_id, language, 'queued', now, now, owner_id))
            return id

    def get(self, id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        for field in ('transcript', 'error'):
            result[field] = json.loads(result[field]) if result[field] else None
        return result

    def get_owned(self, id, owner_id):
        job = self.get(id)
        return job if owner_id and job and job['owner_id'] == owner_id else None

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET status='processing', updated=? WHERE id=?", (time.time(), row['id']))
                return dict(row)
        return None

    def finish(self, id, transcript=None, error=None):
        with self.connect() as db:
            db.execute('UPDATE jobs SET status=?, updated=?, transcript=?, error=? WHERE id=?', ('failed' if error else 'completed', time.time(), json.dumps(transcript) if transcript else None, json.dumps(error) if error else None, id))

    def create_audio(self, path, language, owner_id=None):
        id = uuid4().hex
        now = time.time()
        with self.connect() as db:
            db.execute("INSERT INTO jobs (id,video_id,language,status,created,updated,kind,input_path,owner_id) VALUES (?,?,?,'queued',?,?,'audio',?,?)", (id, 'audio', language, now, now, str(path), owner_id))
        return id
