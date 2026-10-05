import time
import threading
from sqlalchemy.orm import Session
from packages.core.db.session import SessionLocal
from packages.core.db.models import IngestionJob
from packages.core.data.engine import IngestionEngine

class LocalScheduler:
    def __init__(self):
        self._stop = False
        self._thread = None
        
    def start(self):
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        self._stop = True
        if self._thread:
            self._thread.join()
            
    def _loop(self):
        while not self._stop:
            with SessionLocal() as db:
                # Find pending jobs
                job = db.query(IngestionJob).filter(IngestionJob.status == 'PENDING').first()
                if job:
                    engine = IngestionEngine(db)
                    engine.run_ingestion(job.id)
            time.sleep(1)
