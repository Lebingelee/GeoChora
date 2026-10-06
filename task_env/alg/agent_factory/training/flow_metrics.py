"""Auditable Flow losses; validation consumes an isolated, repeatable RNG stream."""
from contextlib import contextmanager
from pathlib import Path
import json
import random
import time
import numpy as np
import torch


@contextmanager
def validation_rng(seed, device):
    python_state, numpy_state = random.getstate(), np.random.get_state()
    devices = [device.index if device.index is not None else torch.cuda.current_device()] if device.type == 'cuda' else []
    try:
        with torch.random.fork_rng(devices=devices):
            random.seed(seed)
            np.random.seed(seed)
            torch.manual_seed(seed)
            if devices:
                with torch.cuda.device(devices[0]):
                    torch.cuda.manual_seed(seed)
            yield
    finally:
        random.setstate(python_state)
        np.random.set_state(numpy_state)


def validation_loss(agent, loader, seed=2026):
    was_training = agent.actor.training
    start = time.monotonic()
    total = samples = batches = 0
    try:
        agent.actor.eval()
        with validation_rng(seed, agent.device), torch.no_grad():
            for batch in loader:
                obs = agent._preprocess_obs(batch['observations'])
                action = agent.normalize_action(batch['action'].to(agent.device).float())
                loss = agent.actor(obs, action)
                if not torch.isfinite(loss):
                    raise ValueError('nonfinite Flow validation loss')
                count = len(action)
                total += float(loss)*count
                samples += count
                batches += 1
    finally:
        agent.actor.train(was_training)
    if not samples:
        raise ValueError('empty validation loader')
    return {'loss': total/samples, 'samples': samples, 'batches': batches,
            'wall_time': time.monotonic()-start}


def train_loop(agent, loader, num_steps, save_dir='', validation_loader=None,
               train_interval=100, validation_interval=1000, validation_seed=2026,
               validation_callback=None):
    if len(loader) == 0 or num_steps <= 0:
        raise ValueError('Flow requires a nonempty loader and positive optimizer budget')
    root = Path(save_dir) if save_dir else None
    if root:
        root.mkdir(parents=True, exist_ok=True)
        if (root/'training_metrics.jsonl').exists():
            raise FileExistsError('refusing to overwrite Flow training history')
    rows = []
    def emit(row):
        rows.append(row)
        if root:
            with (root/'training_metrics.jsonl').open('a') as out:
                out.write(json.dumps(row, allow_nan=False)+'\n')
    start = time.monotonic()
    def validate(step):
        if validation_loader is not None:
            row = {'kind': 'validation', 'step': step,
                   **validation_loss(agent, validation_loader, validation_seed)}
            emit(row)
            if validation_callback is not None:
                validation_callback(agent, row)
    validate(0)
    agent.train()
    iterator = iter(loader)
    window = []
    checkpoint_interval = max(num_steps//4, 1)
    for step in range(1, num_steps+1):
        try:
            batch = next(iterator)
        except StopIteration:
            iterator = iter(loader)
            batch = next(iterator)
        loss = float(agent.update_actor(agent._batch_to_device(batch))['loss_actor'])
        if not np.isfinite(loss):
            raise ValueError('nonfinite Flow training loss')
        window.append(loss)
        agent.step += 1
        if step % train_interval == 0 or step == num_steps:
            emit({'kind': 'train', 'step': step, 'loss': sum(window)/len(window),
                  'window_steps': len(window), 'wall_time': time.monotonic()-start,
                  'learning_rate': agent.actor_optimizer.param_groups[0]['lr']})
            window.clear()
        if step % validation_interval == 0 or step == num_steps:
            validate(step)
        if root and step % checkpoint_interval == 0:
            agent.save(str(root/f'step_{step}.pth'), meta={'mode': 'flow_matching_bc', 'step': step})
    train = [r for r in rows if r['kind'] == 'train']
    val = [r for r in rows if r['kind'] == 'validation']
    best = min(val, key=lambda r: r['loss']) if val else None
    summary = {'schema': 'flow-training-summary-v0', 'initial_train_loss': train[0]['loss'],
               'final_train_loss': train[-1]['loss'], 'minimum_train_window_loss': min(r['loss'] for r in train),
               'initial_validation_loss': val[0]['loss'] if val else None,
               'final_validation_loss': val[-1]['loss'] if val else None,
               'minimum_validation_loss': best['loss'] if best else None,
               'minimum_validation_step': best['step'] if best else None,
               'total_optimizer_steps': num_steps, 'steps_per_epoch': len(loader),
               'epoch_equivalent_count': num_steps/len(loader), 'training_wall_time': time.monotonic()-start}
    if root:
        (root/'training_summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    return summary
