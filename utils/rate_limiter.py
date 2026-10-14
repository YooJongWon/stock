import threading, time

class RateLimiter:
    def __init__(self, requests_per_second: float):
        self.interval=1/max(float(requests_per_second),.01); self.lock=threading.Lock(); self.last=0.0
    def wait(self):
        with self.lock:
            now=time.monotonic(); delay=self.interval-(now-self.last)
            if delay>0: time.sleep(delay)
            self.last=time.monotonic()
