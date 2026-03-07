from django.apps import AppConfig


class OrderConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "Order"

    def ready(self):
        import Order.signals  # noqa: F401 — registers pre_save / post_save handlers
