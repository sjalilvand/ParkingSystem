def test_celery_app_import():
    from app.tasks.celery_app import celery_app
    assert celery_app.main == "parking"


def test_maintenance_task_eager():
    from app.tasks.celery_app import celery_app
    celery_app.conf.task_always_eager = True
    from app.tasks.maintenance import hourly_cleanup
    result = hourly_cleanup.apply()
    assert result.get()["status"] == "ok"


def test_report_task_eager():
    from app.tasks.celery_app import celery_app
    celery_app.conf.task_always_eager = True
    from app.tasks.reports import daily_summary
    result = daily_summary.apply()
    assert result.get()["status"] == "ok"