"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Preserve one native image call and split its packed output into elevations.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image

PROMPT = Path(__file__).with_name('prompts') / 'elevation.md'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserve_copy(source, destination):
    if destination.exists():
        if digest(source) != digest(destination):
            raise FileExistsError(f'Different existing artifact must be preserved: {destination}')
    else:
        shutil.copy2(source, destination)


def split(batch, raw, started, ended):
    reference = json.loads((batch / 'reference.json').read_text())
    started_date = datetime.fromisoformat(started.replace('Z', '+00:00'))
    ended_date = datetime.fromisoformat(ended.replace('Z', '+00:00'))
    elapsed = (ended_date - started_date).total_seconds()
    if elapsed < 0:
        raise ValueError('Call end precedes call start')
    prompt_bytes = PROMPT.read_bytes()
    snapshot = batch / 'prompt-used.md'
    if not snapshot.exists():
        snapshot.write_bytes(prompt_bytes)
    original = batch / 'generated-raw.png'
    preserve_copy(raw, original)
    image = Image.open(original).convert('RGB')
    resized = image.resize(reference['image_size_px'], Image.Resampling.LANCZOS)
    resized_path = batch / 'generated.png'
    resized.save(resized_path)
    now = datetime.now(timezone.utc).isoformat()
    call_id = f"image_gen.imagegen:{reference['id']}:{started}"
    metadata = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'tool': 'image_gen.imagegen', 'call_id': call_id,
                'call_count': 1, 'started_at': started, 'ended_at': ended, 'elapsed_seconds': elapsed,
                'status': 'completed-awaiting-source-masked-verification', 'model': None, 'model_version': None,
                'model_reporting': 'The native image tool did not report a model name or version.',
                'prompt_source': str(PROMPT.resolve()), 'prompt_snapshot': str(snapshot), 'prompt_sha256': digest(snapshot),
                'prompt_snapshot_captured_at': now, 'prompt_source_modified_at': datetime.fromtimestamp(PROMPT.stat().st_mtime, timezone.utc).isoformat(),
                'prompt_source_current_sha256': hashlib.sha256(prompt_bytes).hexdigest(),
                'reference': str(batch / 'reference.png'), 'reference_sha256': digest(batch / 'reference.png'),
                'output_original': str(raw), 'output_raw': str(original), 'output_sha256': digest(original),
                'output_size_px': list(image.size), 'output_resized': str(resized_path), 'split_canvas_size_px': reference['image_size_px'],
                'split_method': 'Resize the entire native output with LANCZOS to the packed reference size, then crop exact recorded pixel rectangles. No per-elevation realignment.',
                'rate_limits_observed': [], 'output_saved_at': now, 'elevations': []}
    for rectangle in reference['elevations']:
        directory = Path(rectangle['reference_image']).parent
        cropped = resized.crop(rectangle['rectangle_px'])
        output = directory / 'generated-raw.png'
        generation_path = directory / 'generation.json'
        if output.exists():
            existing = Image.open(output).convert('RGB')
            if existing.size != cropped.size or existing.tobytes() != cropped.tobytes():
                raise FileExistsError(f'Different existing elevation output must be preserved: {output}')
        else:
            cropped.save(output)
        record = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'tool': 'image_gen.imagegen', 'call_count': 0,
                  'shared_call_id': call_id, 'shared_call_count': 1, 'shared_call_record': str(batch / 'generation.json'),
                  'call_count_basis': 'Derived crop; the single shared model call is counted in its batch generation.json.',
                  'started_at': started, 'ended_at': ended, 'elapsed_seconds': elapsed,
                  'allocated_elapsed_seconds': elapsed / len(reference['elevations']),
                  'status': 'completed-awaiting-source-masked-verification', 'model': None, 'model_version': None,
                  'model_reporting': metadata['model_reporting'], 'prompt_source': str(PROMPT.resolve()),
                  'prompt_snapshot': str(snapshot), 'prompt_sha256': digest(snapshot),
                  'reference': rectangle['reference_image'], 'reference_sha256': digest(Path(rectangle['reference_image'])),
                  'output_original': str(original), 'output_raw': str(output), 'output_sha256': digest(output),
                  'output_size_px': list(cropped.size), 'batch_reference': str(batch / 'reference.json'),
                  'batch_rectangle_px': rectangle['rectangle_px'], 'batch_native_output_size_px': list(image.size),
                  'batch_split_canvas_size_px': reference['image_size_px'], 'split_method': metadata['split_method'],
                  'verified': False, 'verification': None, 'rate_limits_observed': [], 'output_saved_at': now}
        if generation_path.exists():
            previous = json.loads(generation_path.read_text())
            if previous.get('shared_call_id') != call_id:
                raise FileExistsError(f'Different existing generation must be preserved: {generation_path}')
        else:
            generation_path.write_text(json.dumps(record, indent=2) + '\n')
        metadata['elevations'].append({'id': rectangle['elevation_id'], 'directory': str(directory), 'output_raw': str(output), 'rectangle_px': rectangle['rectangle_px']})
    batch_generation = batch / 'generation.json'
    if not batch_generation.exists():
        batch_generation.write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({'batch': str(batch), 'call_id': call_id, 'elapsed_seconds': elapsed, 'native_size_px': list(image.size), 'split_canvas_size_px': reference['image_size_px'], 'elevations': metadata['elevations']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--started', required=True)
    parser.add_argument('--ended', required=True)
    arguments = parser.parse_args()
    split(arguments.batch.resolve(), arguments.raw.resolve(), arguments.started, arguments.ended)
