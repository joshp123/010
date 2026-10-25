#!/usr/bin/env python3
"""Written by AI on 2026-10-25 by model GPT-6 (Codex).

Run inside devenv: python3 tools/measure-speed.py URL
Print two JSON lines: phone and desktop medians of three independent cold/warm
pairs. Raw samples and a separate phone screenshot run go in --output-dir.
Marks are page assertions, not proof of GPU presentation. Missing marks stay null.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


PROBE = """(() => {
  const probe = window.__mapSpeedProbe = {marks: [], frames: [], active: false};
  new PerformanceObserver(list => {
    for (const entry of list.getEntries())
      if (['map-first-view', 'map-complete'].includes(entry.name))
        probe.marks.push({name: entry.name, ms: entry.startTime});
  }).observe({type: 'mark', buffered: true});
  probe.startFrames = () => {
    probe.frames = []; probe.active = true;
    let previous = performance.now();
    function frame(now) {
      if (!probe.active) return;
      probe.frames.push(now - previous); previous = now;
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  };
})();"""


def rounded(value):
    return round(value, 2) if value is not None else None


def median(values):
    present = [value for value in values if value is not None]
    # An incomplete set must not silently become a passing median.
    return rounded(statistics.median(present)) if len(present) == len(values) and present else None


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class NetworkMeasurement:
    """CDP encoded bytes (headers + compressed body), including partial requests."""
    def __init__(self, session, context):
        self.context = context
        self.requests = {}
        self.redirects = []
        session.on('Network.requestWillBeSent', self.request)
        session.on('Network.responseReceived', self.response)
        session.on('Network.requestServedFromCache', self.cached)
        session.on('Network.dataReceived', self.data)
        session.on('Network.loadingFinished', self.finished)
        session.on('Network.loadingFailed', self.failed)

    def reset(self):
        self.requests = {}
        self.redirects = []

    def request(self, event):
        if not event['request']['url'].startswith(('http:', 'https:')):
            return
        identifier = event['requestId']
        if 'redirectResponse' in event:
            previous = self.requests.pop(identifier, None)
            if previous:
                previous.update(bytes=event['redirectResponse'].get('encodedDataLength', 0), done=True)
                self.redirects.append(previous)
        self.requests[identifier] = dict(type=event.get('type', 'Other').lower(), bytes=0,
                                         cache=False, service_worker=False, done=False, failed=False)

    def response(self, event):
        request = self.requests.get(event['requestId'])
        if request is not None:
            response = event['response']
            request.update(type=event.get('type', 'Other').lower(),
                           bytes=response.get('encodedDataLength', 0),
                           cache=request['cache'] or response.get('fromDiskCache', False),
                           service_worker=response.get('fromServiceWorker', False))

    def cached(self, event):
        if event['requestId'] in self.requests:
            self.requests[event['requestId']]['cache'] = True

    def data(self, event):
        if event['requestId'] in self.requests:
            self.requests[event['requestId']]['bytes'] += event.get('encodedDataLength', 0)

    def finished(self, event):
        if event['requestId'] in self.requests:
            self.requests[event['requestId']].update(bytes=event['encodedDataLength'], done=True)

    def failed(self, event):
        if event['requestId'] in self.requests:
            self.requests[event['requestId']].update(done=True, failed=True)

    def snapshot(self):
        requests = list(self.requests.values()) + self.redirects
        by_type = {}
        for request in requests:
            transferred = 0 if request['cache'] or request['service_worker'] else max(0, request['bytes'])
            by_type[request['type']] = by_type.get(request['type'], 0) + transferred
        worker_responses = sum(r['service_worker'] for r in requests)
        worker_traffic_unobserved = bool(worker_responses or self.context.service_workers)
        return dict(transferred_bytes=None if worker_traffic_unobserved else round(sum(by_type.values())),
                    request_count=None if worker_traffic_unobserved else len(requests),
                    bytes_by_type={key: None if worker_traffic_unobserved else round(value)
                                   for key, value in sorted(by_type.items())},
                    observed_page_bytes=round(sum(by_type.values())), observed_page_requests=len(requests),
                    transfer_limitation='worker network traffic is outside the page CDP session' if worker_traffic_unobserved else None,
                    cached_requests=sum(r['cache'] for r in requests),
                    service_worker_requests=sum(r['service_worker'] for r in requests),
                    failed_requests=sum(r['failed'] for r in requests),
                    pending_requests=sum(not r['done'] for r in requests))


async def configure(playwright, phone, profile_directory):
    context = await playwright.chromium.launch_persistent_context(
        str(profile_directory), headless=True,
        args=['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'],
        viewport={'width': 390 if phone else 1440, 'height': 844 if phone else 900},
        device_scale_factor=3 if phone else 1, is_mobile=phone, has_touch=True,
        **({'user_agent': 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36'} if phone else {}))
    await context.add_init_script(PROBE)
    page = context.pages[0]
    session = await context.new_cdp_session(page)
    await session.send('Network.enable')
    if phone:
        await session.send('Network.emulateNetworkConditions', dict(
            offline=False, latency=80, downloadThroughput=20_000_000 / 8,
            uploadThroughput=5_000_000 / 8, connectionType='cellular4g'))
        await session.send('Emulation.setCPUThrottlingRate', {'rate': 4})
    return context, page, session


async def mark_state(page):
    return await page.evaluate('''() => ({marks: window.__mapSpeedProbe.marks,
        now: performance.now(), map_ready: window.mapReady === true})''')


async def visit(page, network, url, timeout_seconds, reload=False):
    network.reset()
    errors = []
    on_error = lambda error: errors.append(str(error))
    page.on('pageerror', on_error)
    started = time.monotonic()
    navigation_error = None
    status = None
    try:
        response = await (page.reload(wait_until='commit', timeout=timeout_seconds * 1000) if reload
                          else page.goto(url, wait_until='commit', timeout=timeout_seconds * 1000))
        status = response.status if response else None
        remaining = max(1, (timeout_seconds - (time.monotonic() - started)) * 1000)
        await page.wait_for_function(
            "window.__mapSpeedProbe?.marks.some(mark => mark.name === 'map-complete')",
            timeout=remaining, polling=25)
    except PlaywrightTimeoutError:
        navigation_error = 'marks_or_navigation_timeout'
    snapshot = network.snapshot()
    state = await mark_state(page)
    marks = state['marks']
    first = next((m['ms'] for m in marks if m['name'] == 'map-first-view'), None)
    complete = next((m['ms'] for m in marks if m['name'] == 'map-complete'), None)
    page.remove_listener('pageerror', on_error)
    return dict(first_view_ms=rounded(first), complete_ms=rounded(complete), **snapshot,
                network_observation_ms=rounded(state['now']), http_status=status,
                missing_marks=[name for name, value in [('map-first-view', first), ('map-complete', complete)]
                               if value is None], map_ready=state['map_ready'],
                error=navigation_error, page_errors=errors)


async def pan(page, session, phone, timeout_seconds):
    width, height = (390, 844) if phone else (1440, 900)
    swipes = []
    frame_times = []
    for swipe in range(5):
        # All five move left by 200 CSS px, at mid-height, clear of page controls.
        x, y = width / 2 + 100, height / 2
        initial = await mark_state(page)
        await page.evaluate('window.__mapSpeedProbe.startFrames()')
        started = await page.evaluate('performance.now()')
        await session.send('Input.dispatchTouchEvent', dict(type='touchStart',
                           touchPoints=[dict(x=x, y=y, id=1)]))
        gesture_started = time.monotonic()
        for step in range(1, 19):
            await asyncio.sleep(max(0, gesture_started + step / 60 - time.monotonic()))
            await session.send('Input.dispatchTouchEvent', dict(type='touchMove',
                               touchPoints=[dict(x=x - 200 * step / 18, y=y, id=1)]))
        await session.send('Input.dispatchTouchEvent', dict(type='touchEnd', touchPoints=[]))
        ended = await page.evaluate('performance.now()')
        frames = await page.evaluate('''() => {
            window.__mapSpeedProbe.active = false; return window.__mapSpeedProbe.frames;
        }''')
        # The first rAF interval is partial; all subsequent intervals span two callbacks.
        frame_times.extend(frames[1:])
        try:
            await page.wait_for_function('''end => window.__mapSpeedProbe.marks.some(
                mark => mark.name === 'map-complete' && mark.ms >= end)''',
                arg=ended, timeout=timeout_seconds * 1000, polling=25)
        except PlaywrightTimeoutError:
            pass
        final = await mark_state(page)
        new_marks = [m['ms'] for m in final['marks'][len(initial['marks']):]
                     if m['name'] == 'map-complete']
        after_end = next((value for value in new_marks if value >= ended), None)
        swipes.append(dict(gesture_ms=rounded(ended - started),
                           complete_marks_during_gesture=sum(value < ended for value in new_marks),
                           complete_after_release_ms=rounded(after_end - ended) if after_end is not None else None,
                           observation_after_release_ms=rounded(final['now'] - ended)))
    return dict(frame_median_ms=rounded(statistics.median(frame_times)) if frame_times else None,
                frame_p95_ms=rounded(percentile(frame_times, .95)),
                frame_longest_ms=rounded(max(frame_times)) if frame_times else None,
                frame_count=len(frame_times),
                complete_after_release_ms=median([s['complete_after_release_ms'] for s in swipes]),
                swipes_with_complete_after_release=sum(s['complete_after_release_ms'] is not None for s in swipes),
                swipes=swipes)


async def screenshots(playwright, url, directory, timeout_seconds):
    # Kept outside measured trials: PNG encoding/readback can stall the renderer.
    context, page, session = await configure(playwright, True, directory / 'profiles' / 'screenshots')
    try:
        await page.goto(url, wait_until='commit', timeout=timeout_seconds * 1000)
        captures = {}
        deadline = time.monotonic() + timeout_seconds
        for label, mark in [('first-view', 'map-first-view'), ('complete', 'map-complete')]:
            try:
                await page.wait_for_function(
                    'name => window.__mapSpeedProbe.marks.some(mark => mark.name === name)', arg=mark,
                    timeout=max(1, (deadline - time.monotonic()) * 1000), polling=10)
            except PlaywrightTimeoutError:
                pass
            before = await mark_state(page)
            observed = any(m['name'] == mark for m in before['marks'])
            path = directory / f'phone-{label}{"" if observed else "-missing"}.png'
            await page.screenshot(path=str(path), timeout=30_000)
            captures[label] = dict(path=str(path), mark_observed=observed,
                                   before_capture=before, after_capture=await mark_state(page))
        return captures
    finally:
        await context.close()


def summarize(samples, section, keys):
    return {key: median([sample[section][key] for sample in samples]) for key in keys}


async def main(args):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    directory = args.output_dir / f'{urlparse(args.url).hostname}-{stamp}'
    directory.mkdir(parents=True, exist_ok=False)
    async with async_playwright() as playwright:
        for phone in (True, False):
            profile = 'phone' if phone else 'desktop'
            samples = []
            for repetition in range(3):
                print(f'{profile}: cold/warm/pan {repetition + 1}/3', file=sys.stderr, flush=True)
                context, page, session = await configure(playwright, phone,
                                                        directory / 'profiles' / f'{profile}-{repetition + 1}')
                try:
                    network = NetworkMeasurement(session, context)
                    cold = await visit(page, network, args.url, args.timeout)
                    print(f'  cold: first={cold["first_view_ms"]} complete={cold["complete_ms"]} ms', file=sys.stderr, flush=True)
                    warm = await visit(page, network, args.url, args.timeout, reload=True)
                    print(f'  warm: first={warm["first_view_ms"]} complete={warm["complete_ms"]} ms', file=sys.stderr, flush=True)
                    # Without completion, retain observed frames but do not assert the map is loaded.
                    pan_result = await pan(page, session, phone, args.pan_timeout)
                    pan_result['loaded_before_pan'] = warm['complete_ms'] is not None
                    samples.append(dict(cold=cold, warm=warm, pan=pan_result))
                    (directory / f'{profile}-samples.json').write_text(json.dumps(samples, indent=2) + '\n')
                    browser_version = context.browser.version
                finally:
                    await context.close()
            raw_path = directory / f'{profile}-samples.json'
            raw_path.write_text(json.dumps(samples, indent=2) + '\n')
            result = dict(url=args.url, profile=profile, repetitions=3, browser=browser_version,
                          viewport=[390, 844] if phone else [1440, 900], device_scale_factor=3 if phone else 1,
                          touch=True, cpu_slowdown=4 if phone else 1,
                          network=dict(down_mbps=20, up_mbps=5, latency_ms=80) if phone else None,
                          aggregation='median across three trials; null if any trial is missing', samples_path=str(raw_path))
            for section in ('cold', 'warm'):
                result[section] = summarize(samples, section, [
                    'first_view_ms', 'complete_ms', 'transferred_bytes', 'request_count',
                    'cached_requests', 'service_worker_requests', 'failed_requests', 'pending_requests'])
                types = sorted({key for s in samples for key in s[section]['bytes_by_type']})
                result[section]['bytes_by_type'] = {
                    key: median([s[section]['bytes_by_type'].get(key, 0) for s in samples]) for key in types}
                result[section]['first_view_mark_runs'] = sum(s[section]['first_view_ms'] is not None for s in samples)
                result[section]['complete_mark_runs'] = sum(s[section]['complete_ms'] is not None for s in samples)
                result[section]['timeout_runs'] = sum(s[section]['error'] is not None for s in samples)
                result[section]['page_error_count'] = sum(len(s[section]['page_errors']) for s in samples)
                result[section]['transfer_limitation'] = next((s[section]['transfer_limitation'] for s in samples
                                                               if s[section]['transfer_limitation']), None)
            result['pan'] = summarize(samples, 'pan', ['frame_median_ms', 'frame_p95_ms', 'frame_longest_ms',
                                                       'complete_after_release_ms', 'swipes_with_complete_after_release'])
            result['pan'].update(swipes=5, distance_css_px=200, target_gesture_ms=300,
                                  observation_after_release_limit_ms=args.pan_timeout * 1000,
                                  loaded_runs=sum(s['pan']['loaded_before_pan'] for s in samples))
            result['slo_ms'] = dict(warm_first_view=100, pan_content_after_release=100,
                                    cold_first_view=340 if phone else None,
                                    cold_phone_assumed_network_floor=240 if phone else None)
            result['screenshots'] = (await screenshots(playwright, args.url, directory, args.timeout)
                                     if phone and any(s['cold']['first_view_ms'] is not None for s in samples) else None)
            (directory / f'{profile}-summary.json').write_text(json.dumps(result, indent=2) + '\n')
            print(json.dumps(result, separators=(',', ':')), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--output-dir', type=Path,
                        default=Path('/Volumes/Josh Extreme Pro USB4 4TB/010/renders/speed'))
    parser.add_argument('--timeout', type=float, default=240, help='seconds per navigation, including marks (default: 240)')
    parser.add_argument('--pan-timeout', type=float, default=2, help='seconds to observe completion after each swipe (default: 2)')
    arguments = parser.parse_args()
    if urlparse(arguments.url).scheme not in ('http', 'https') or arguments.timeout <= 0 or arguments.pan_timeout <= 0:
        parser.error('URL must be HTTP(S), and timeouts must be positive')
    asyncio.run(main(arguments))
