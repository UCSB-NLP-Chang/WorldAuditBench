"""Read physical NVIDIA load without CUDA/Vulkan enumeration side effects."""
import csv
import io
import math
import subprocess


def sample_gpus():
    text = subprocess.check_output([
        'nvidia-smi', '--query-gpu=index,uuid,memory.total,memory.used,utilization.gpu',
        '--format=csv,noheader,nounits'], text=True, timeout=3)
    result = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) != 5:
            raise ValueError('Incomplete GPU telemetry')
        index = int(row[0]); total, used, utilization = map(float, row[2:])
        if index in result or not all(math.isfinite(x) for x in (total, used, utilization)):
            raise ValueError('Invalid GPU telemetry')
        if not 0 <= used <= total or total <= 0 or not 0 <= utilization <= 100:
            raise ValueError('GPU telemetry out of range')
        result[index] = dict(uuid=row[1].strip(), total_mb=total,
                             used_mb=used, utilization=utilization)
    if not result:
        raise ValueError('No GPUs available')
    return result
