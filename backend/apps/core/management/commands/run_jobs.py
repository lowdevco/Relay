import time

from django.core.management.base import BaseCommand

from apps.core import jobs


class Command(BaseCommand):
    help = "Process pending background jobs (AI replies, media download, voice notes)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process due jobs once and exit.")
        parser.add_argument("--interval", type=float, default=2.0)

    def handle(self, *args, once=False, interval=2.0, **options):
        jobs._ensure_handlers_loaded()
        self.stdout.write("Job worker started.")
        while True:
            jobs.requeue_stale()
            ids = jobs.due_jobs()
            for job_id in ids:
                ok = jobs.run_job(job_id)
                self.stdout.write(f"job {job_id}: {'done' if ok else 'failed/retry'}")
            if once:
                return
            if not ids:
                time.sleep(interval)
