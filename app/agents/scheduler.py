"""The WaitlistAgent's clock: runs its expiry sweep every 30 seconds with no user action."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.agents.registry import setup_agents
from app.config import APP_ENV
from app.database import SessionLocal

SWEEP_SECONDS = 30
log = logging.getLogger("eventsphere.scheduler")
_scheduler = None


def _sweep_job():
    db = SessionLocal()
    try:
        expired = setup_agents()["WaitlistAgent"].tick(db)
        db.commit()
        if expired:
            log.info("WaitlistAgent expired %s hold(s)", expired)
    except Exception:                      # never let the timer thread die
        db.rollback()
        log.exception("waitlist sweep failed")
    finally:
        db.close()


def start_scheduler():
    global _scheduler
    if _scheduler is not None or APP_ENV == "test":
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_sweep_job, "interval", seconds=SWEEP_SECONDS, id="waitlist_sweep")
    _scheduler.start()


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
