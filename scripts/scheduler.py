"""Local scheduler for retraining using APScheduler.

Usage: run this as a background process on a host to schedule periodic retrains.
"""
import os
import logging
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from subprocess import Popen

load_dotenv()

RETRAIN_INTERVAL_HOURS = int(os.getenv('RETRAIN_INTERVAL_HOURS', '24'))
RETRAIN_SCRIPT = os.path.join(os.path.dirname(__file__), 'retrain_runner.py')
LOG_LEVEL = os.getenv('SCHED_LOG_LEVEL', 'INFO')

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger('retrain-scheduler')


def run_retrain():
    logger.info('Starting retrain runner subprocess')
    # run in subprocess so that lock lifetime is bounded to the process
    p = Popen(["python", RETRAIN_SCRIPT])
    p.wait()
    logger.info('Retrain runner finished with exit %s', p.returncode)


def main():
    sched = BlockingScheduler()
    trigger = IntervalTrigger(hours=RETRAIN_INTERVAL_HOURS)
    sched.add_job(run_retrain, trigger, id='retrain-job', replace_existing=True)
    logger.info('Scheduler started: interval %s hours', RETRAIN_INTERVAL_HOURS)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info('Scheduler stopped')


if __name__ == '__main__':
    main()
