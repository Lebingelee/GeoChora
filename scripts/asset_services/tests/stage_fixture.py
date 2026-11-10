# 作用：记录模拟阶段的实际执行区间，必要时与另一资源的阶段握手。
# 输入输出：名称、耗时、信号目录、对端名称 -> 当前任务目录中的阶段时间 JSON。
import json
from pathlib import Path
import sys
import time


if __name__ == '__main__':
    name, seconds, signals, peer = sys.argv[1:]
    started = time.monotonic()
    signals = Path(signals)
    (signals / f'{name}.started').touch()
    if peer != '-':
        deadline = time.monotonic() + 8
        while not (signals / f'{peer}.started').exists():
            if time.monotonic() > deadline:
                raise RuntimeError('另一资源没有并行启动')
            time.sleep(0.01)
    time.sleep(float(seconds))
    Path(f'{name}.json').write_text(json.dumps({'start': started, 'end': time.monotonic()}))
    Path('result.json').write_text(json.dumps({
        'artifacts': {p.stem: str(p.resolve()) for p in Path.cwd().glob('*.json') if p.name != 'result.json'},
        'metadata': {},
    }), encoding='utf-8')
