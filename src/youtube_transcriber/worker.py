from dataclasses import asdict
import logging
from pathlib import Path
from threading import Event, Thread

from .models import TranscriptError

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, store, provider, retry_delay=1, speech_provider=None):
        self.store, self.provider, self.retry_delay = store, provider, retry_delay
        self.speech_provider = speech_provider
        self.stop = Event()
        self.thread = Thread(target=self.run, daemon=True, name='caption-worker')

    def start(self):
        self.store.recover()
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join()

    def run(self):
        while not self.stop.is_set():
            job = self.store.claim()
            if job is None:
                self.stop.wait(.1)
                continue
            for attempt in range(3):
                try:
                    if job['kind'] == 'audio':
                        transcript = self.speech_provider.fetch_file(job['input_path'], job['language'])
                    else:
                        transcript = self.provider.fetch(job['video_id'], job['language'])
                    self.store.finish(job['id'], transcript=asdict(transcript))
                    self.cleanup(job)
                    logger.info('job_completed id=%s source=%s', job['id'], transcript.source)
                    break
                except TranscriptError as exc:
                    if exc.code == 'temporary_failure' and attempt < 2:
                        if self.stop.wait(self.retry_delay * (2 ** attempt)):
                            return
                        continue
                    self.store.finish(job['id'], error={'code': exc.code, 'message': str(exc)})
                    self.cleanup(job)
                    logger.info('job_failed id=%s code=%s', job['id'], exc.code)
                    break
                except Exception:
                    logger.exception('unexpected_job_failure id=%s', job['id'])
                    self.store.finish(job['id'], error={'code': 'internal_error', 'message': 'An unexpected processing error occurred.'})
                    self.cleanup(job)
                    break

    def cleanup(self, job):
        if job['kind'] == 'audio':
            try:
                Path(job['input_path']).unlink(missing_ok=True)
            except OSError:
                logger.warning('audio_cleanup_deferred id=%s', job['id'])
