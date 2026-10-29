"""Bounded asynchronous public preamble/header observer; no body decoding."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import time
import numpy as np
from .protocol import PREAMBLE, HEADER_BITS, parse_header
from .receiver import find_preamble, sample_slots
from .screen_capture_packet import bit_duration, positive


def observe(times, brightness, bit_ms):
    t, y = np.asarray(times), np.asarray(brightness)
    if len(t) < 40 or np.ptp(y) < 20:
        return None
    try:
        sync = find_preamble(t,y,bit_ms)
        values,_ = sample_slots(t,y,sync['start_seconds'],sync['period_seconds'],
                                range(len(PREAMBLE),len(PREAMBLE)+HEADER_BITS))
        header = parse_header((values>sync['threshold']).astype(np.uint8))
        return dict(estimated_preamble_start=sync['start_seconds'], codec=header['codec'],
                    sequence=header['sequence'],payload_bytes=header['payload_bytes'])
    except (ValueError, IndexError):
        return None


class HeaderObserver:
    def __init__(self, bit_ms=200, max_samples=20000):
        self.bit_ms = bit_duration(bit_ms)
        self.window = (len(PREAMBLE)+HEADER_BITS+16)*bit_ms/1000
        self.samples = deque(maxlen=max_samples)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.last_attempt = -float('inf')
        self.dropped_jobs = 0
        self.max_samples = max_samples
        self.last_start = -float('inf')

    def feed(self, timestamp, brightness):
        self.samples.append((timestamp,brightness))
        while self.samples and timestamp-self.samples[0][0] > self.window:
            self.samples.popleft()
        result = None
        if self.future is not None and self.future.done():
            result = self.future.result()
            self.future = None
            if result and result['estimated_preamble_start'] <= self.last_start+self.bit_ms/1000:
                result = None
            if result:
                self.last_start = result['estimated_preamble_start']
        if timestamp-self.last_attempt >= 1:
            self.last_attempt = timestamp
            if self.future is None and len(self.samples)>=40:
                t,y = zip(*self.samples)
                self.future = self.executor.submit(observe,t,y,self.bit_ms)
            else:
                self.dropped_jobs += 1
        return result

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


class FirstPacketTimer:
    def __init__(self, budget):
        self.budget = positive(budget)
        self.armed = None
        self.deadline = None
        self.source = None
        self.observation = None

    def arm(self, now, source, observation=None):
        if self.armed is None:
            self.armed, self.deadline = now, now+self.budget
            self.source, self.observation = source, observation

    def expired(self, now):
        return self.deadline is not None and now >= self.deadline
