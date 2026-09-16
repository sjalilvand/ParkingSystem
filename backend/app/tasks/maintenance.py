from app.tasks.celery_app import celery_app


@celery_app.task(name="tasks.maintenance.hourly_cleanup")
def hourly_cleanup():
    # placeholder: purge expired files from MinIO per retention policy
    return {"status": "ok", "cleaned": 0}