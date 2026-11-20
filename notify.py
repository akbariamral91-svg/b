# -*- coding: utf-8 -*-
"""ارسال اعلان سیستمی (اختیاری). اگر بستهٔ flet-local-notifications نصب نباشد یا خطا بدهد، فقط پیام داخل برنامه نشان داده می‌شود.
منطق «چه چیزی و کی» در store.reminders_due است؛ اینجا فقط تحویل پیام انجام می‌شود."""
import asyncio

try:
    from flet_local_notifications import FletLocalNotification, AndroidNotificationConfig, DesktopNotificationConfig
    AVAILABLE = True
except Exception:                                   # نصب نیست؛ مشکلی نیست
    FletLocalNotification = AndroidNotificationConfig = DesktopNotificationConfig = None
    AVAILABLE = False

class Notifier:
    def __init__(self, page, on_error=None):
        self.page, self.on_error, self.n, self.ready = page, on_error or (lambda *a: None), None, False
        if not AVAILABLE: return
        try: self.n = FletLocalNotification(page); self.ready = True
        except Exception as ex: self.on_error("notifier init", ex)

    def send(self, title, body):
        """اعلان سیستمی را همین الان نشان می‌دهد؛ True اگر ارسال شروع شد."""
        if not self.ready: return False
        async def go():
            try:
                await self.n.send(AndroidNotificationConfig(title=title, message=body),
                                  DesktopNotificationConfig(title=title, message=body, app_name="Get Better"))
            except Exception as ex: self.on_error("notify send", ex)
        try: self.page.run_task(go); return True
        except Exception as ex: self.on_error("notify run_task", ex); return False
