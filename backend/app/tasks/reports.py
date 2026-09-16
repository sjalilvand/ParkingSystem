from app.tasks.celery_app import celery_app


@celery_app.task(name="tasks.reports.daily_summary")
def daily_summary():
    # placeholder: build and store daily PDF/Excel report
    return {"status": "ok", "report": "daily_summary"}