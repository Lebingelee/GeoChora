"""Frozen Flow policy-search variants on the completed 100 Hz corpus.

This is an exploratory learner-side route.  It never collects trajectories and
does not change the public controller or canonical trajectory contract.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import random
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from omegaconf import OmegaConf
import yaml

import task_env.alg.agent_factory
from agent_factory.agents.registry import make_agent
from agent_factory.training.identity import config_identity, digest
from task_env.alg.state_bc.features import ACTION_CONTRACT, FEATURE_CONTRACT
from task_env.diagnostics.phase1 import flow_training_normalized as baseline
from .flow100_data import Flow100Dataset, observation_contract


BASE = Path("workspace/experiments/p1_6_policy_search/100hz_gpu_flow")
MANIFEST = BASE / "training_dataset_manifest_100hz.json"
MANIFEST_LOCK = BASE / "training_dataset_manifest_100hz_lock.json"
V0_TRAIN = BASE / "flow_training"
EPOCHS = 80
SEED = 2026
DEVICE = "cuda"
EXPECTED_MANIFEST_SHA256 = "0e13517ce9f179daf7d4c525a6fb7d33629d3bb6fdd7683b4f06ac9492cf10dd"
VARIANTS = {
    "v1": {
        "directory": "100hz_gpu_flow_h50_a36_v1",
        "agent_type": "Flow_Vanilla",
        "pred_horizon": 50,
        "act_horizon": 36,
        "excluded_fields": (),
        "display_name": "Flow h50/a36 full 33D state",
    },
    "v2": {
        "directory": "100hz_gpu_flow_h50_a36_no_qvel_v2",
        "agent_type": "Flow_Vanilla",
        "pred_horizon": 50,
        "act_horizon": 36,
        "excluded_fields": ("arm_velocity7",),
        "display_name": "Flow h50/a36 without arm velocity",
    },
}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path) -> str:
    return sha_bytes(Path(path).read_bytes())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite policy-search evidence: {path}")
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def write_yaml_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite policy-search evidence: {path}")
    path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True))


def _variant(name):
    try:
        value = dict(VARIANTS[name])
    except KeyError as exc:
        raise ValueError(f"unknown Flow policy-search variant: {name}") from exc
    value["name"] = name
    value["root"] = Path("workspace/experiments/p1_6_policy_search") / value["directory"]
    value["training_root"] = value["root"] / "training"
    return value


def _verify_dataset():
    if not MANIFEST.is_file() or not MANIFEST_LOCK.is_file():
        raise FileNotFoundError("frozen 100 Hz successful corpus is unavailable")
    actual = sha(MANIFEST)
    lock = json.loads(MANIFEST_LOCK.read_text())
    if actual != EXPECTED_MANIFEST_SHA256 or lock.get("sha256") != actual:
        raise ValueError("policy_search_dataset_identity: 100 Hz dataset SHA mismatch")
    manifest = json.loads(MANIFEST.read_text())
    if (manifest.get("schema") != "p1_6-100hz-flow-dataset-v0"
            or manifest.get("logical_identity") != "f2ebc763dd98ec5c78ec77c2d988255ec112ca24e331afebeea2fe45a5bff478"
            or manifest.get("execution_backend") != "cuda"
            or len(manifest.get("selected_train_seeds", ())) != 80
            or len(manifest.get("selected_validation_seeds", ())) != 20
            or not manifest.get("full_training_authorized")):
        raise ValueError("policy_search_dataset_identity: frozen 80/20 corpus contract mismatch")
    return manifest, actual


def _base_config(profile, batch_size, steps_per_epoch, dataset_sha):
    cfg = baseline.load_variant_config(V0_TRAIN / "resolved_flow_config.yaml")
    cfg.dataset.expert.demo_path = str(MANIFEST)
    cfg.dataset.config = {"allow_failed_for_smoke": False}
    cfg.env.obs_horizon = 2
    cfg.env.pred_horizon = profile["pred_horizon"]
    cfg.env.act_horizon = profile["act_horizon"]
    cfg.env.proprio_dim = observation_contract(profile["excluded_fields"])["state_dim"]
    cfg.actor.obs_horizon = 2
    cfg.actor.pred_horizon = profile["pred_horizon"]
    cfg.actor.encoder.proprio_dim = cfg.env.proprio_dim
    cfg.train.actor_iters = EPOCHS * int(steps_per_epoch)
    cfg.train.batch_size = int(batch_size)
    cfg.train.device = DEVICE
    cfg.device = DEVICE
    cfg.train.save_root = str(profile["training_root"] / "agent_run")
    cfg.train.exp_name = f"{profile['name']}_{profile['agent_type']}_h{profile['pred_horizon']}_a{profile['act_horizon']}"
    contract = observation_contract(profile["excluded_fields"])
    identities = {
        "resolved_config_sha256": config_identity(cfg),
        "dataset_manifest_sha256": dataset_sha,
        "agent_type": profile["agent_type"],
        "feature_contract_identity": contract["identity"],
        "action_contract_identity": digest(ACTION_CONTRACT),
    }
    cfg.agent_sp.artifact_identity = identities
    if config_identity(cfg) != identities["resolved_config_sha256"]:
        raise ValueError("resolved Flow config identity is unstable")
    if (cfg.agent_type != profile["agent_type"] or cfg.agent_control_mode != "absolute_joint"
            or cfg.env.env_control_mode != "absolute_joint" or cfg.device != "cuda"
            or cfg.train.device != "cuda" or cfg.actor.num_inference_steps != 10
            or cfg.actor.lr != 1e-4 or cfg.actor.weight_decay != 1e-6
            or cfg.actor.norm.type != "quantile" or cfg.actor.norm.params.q_low != .01
            or cfg.actor.norm.params.q_high != .99 or cfg.actor.norm.params.clip is not True
            or cfg.actor.obs_norm.type != "mean_std"):
        raise ValueError("Flow config diverged from frozen 100 Hz V0 training semantics")
    return cfg, identities


def _seed_all():
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)


def _normalizer_state(agent):
    return {
        "action": {k: v.detach().cpu().clone() for k, v in agent.action_normalizer.state_dict().items()},
        "observation": {k: v.detach().cpu().clone() for k, v in agent.obs_normalizer.state_dict().items()},
    }


def _normalizer_json(state):
    return {part: {key: tensor.tolist() for key, tensor in values.items()}
            for part, values in state.items()}


def _probe_batch_size(profile, train_ds, val_ds, manifest_sha):
    """Select only from the mandated 512 -> 256 -> 128 OOM fallback sequence."""
    attempts = []
    for batch_size in (512, 256, 128):
        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False,
                                  drop_last=True, num_workers=0)
        if len(train_loader) < 1:
            attempts.append({"batch_size": batch_size, "result": "no_full_batch"})
            continue
        cfg, identities = _base_config(profile, batch_size, len(train_loader), manifest_sha)
        agent = None
        started = time.perf_counter()
        try:
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            _seed_all()
            agent = make_agent(profile["agent_type"], cfg)
            states = train_ds.get_all_states().float().to(agent.device)
            actions = train_ds.get_all_actions().float().to(agent.device)
            agent.fit_obs_normalizer(states)
            agent.fit_action_normalizer(actions)
            batch = next(iter(train_loader))
            metrics = agent.update_actor(batch)
            torch.cuda.synchronize()
            loss = float(metrics["loss_actor"])
            if not np.isfinite(loss):
                raise ValueError("non-finite disposable batch-smoke loss")
            attempts.append({"batch_size": batch_size, "result": "pass", "loss": loss,
                             "wall_time_s": time.perf_counter() - started,
                             "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                             "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                             "config_identity": identities["resolved_config_sha256"]})
            return batch_size, attempts
        except (torch.cuda.OutOfMemoryError, RuntimeError) as exc:
            is_oom = isinstance(exc, torch.cuda.OutOfMemoryError) or "out of memory" in str(exc).lower()
            if not is_oom:
                raise
            attempts.append({"batch_size": batch_size, "result": "cuda_oom",
                             "error_type": type(exc).__name__, "error": str(exc)[:500]})
        finally:
            del agent
            torch.cuda.empty_cache()
    raise RuntimeError("Flow batch-size fallback exhausted: " + json.dumps(attempts))


def prepare(name):
    profile = _variant(name)
    root = profile["root"]
    if root.exists() and any(p.name != "design_note.md" for p in root.iterdir()):
        raise FileExistsError(f"variant root already contains Evidence: {root}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable for frozen Flow policy-search profile")
    manifest, manifest_sha = _verify_dataset()
    train_ds = Flow100Dataset(MANIFEST, "train", pred_horizon=profile["pred_horizon"],
                              excluded_fields=profile["excluded_fields"])
    val_ds = Flow100Dataset(MANIFEST, "validation", pred_horizon=profile["pred_horizon"],
                            excluded_fields=profile["excluded_fields"])
    if (train_ds.statistics["trajectory_count"], val_ds.statistics["trajectory_count"],
            train_ds.get_all_states().shape[1], val_ds.get_all_states().shape[1]) != (80, 20,
                observation_contract(profile["excluded_fields"])["state_dim"],
                observation_contract(profile["excluded_fields"])["state_dim"]):
        raise ValueError("frozen corpus or selected feature dimension mismatch")
    batch_size, batch_attempts = _probe_batch_size(profile, train_ds, val_ds, manifest_sha)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                              drop_last=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                            drop_last=False, num_workers=0)
    steps_per_epoch = len(train_loader)
    actor_iters = EPOCHS * steps_per_epoch
    cfg, identities = _base_config(profile, batch_size, steps_per_epoch, manifest_sha)
    root.mkdir(parents=True, exist_ok=True)
    profile["training_root"].mkdir(parents=True, exist_ok=True)
    resolved_path = root / "resolved_config.yaml"
    OmegaConf.save(cfg, resolved_path, resolve=True)
    config_sha = config_identity(baseline.load_variant_config(resolved_path))
    if config_sha != identities["resolved_config_sha256"]:
        raise ValueError("saved resolved Flow config identity mismatch")
    states = train_ds.get_all_states().float()
    actions = train_ds.get_all_actions().float()
    action_q01 = torch.quantile(actions, .01, dim=0)
    action_q99 = torch.quantile(actions, .99, dim=0)
    state_stats = {"min": states.amin(0).tolist(), "max": states.amax(0).tolist(),
                   "mean": states.mean(0).tolist(), "std_unbiased": states.std(0).tolist()}
    action_stats = {"min": actions.amin(0).tolist(), "max": actions.amax(0).tolist(),
                    "mean": actions.mean(0).tolist(), "std_unbiased": actions.std(0).tolist(),
                    "q01": action_q01.tolist(), "q99": action_q99.tolist()}
    training_spec = {
        "schema": "p1_6-100hz-flow-search-training-spec-v0",
        "variant": name,
        "description": profile["display_name"],
        "baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "locked_before_governed_training": True,
        "dataset": {"manifest_path": str(MANIFEST), "file_sha256": manifest_sha,
                    "logical_identity": manifest["logical_identity"],
                    "execution_backend": manifest["execution_backend"],
                    "train_seeds": manifest["selected_train_seeds"],
                    "validation_seeds": manifest["selected_validation_seeds"],
                    "train_trajectory_count": 80, "validation_trajectory_count": 20,
                    "train_samples": len(train_ds), "validation_samples": len(val_ds)},
        "temporal_profile": {"physics_dt_s": .002, "control_substeps": 5, "control_dt_s": .010,
                             "physics_hz": 500, "control_hz": 100},
        "learner": {"agent_type": profile["agent_type"], "backbone": "ConditionalUnet1D",
                    "state_dim": int(states.shape[1]), "raw_state_dim": 33,
                    "observation_contract": train_ds.observation,
                    "action_contract": ACTION_CONTRACT, "action_dim": 8,
                    "action_mode": "absolute_joint", "obs_horizon": 2,
                    "pred_horizon": profile["pred_horizon"], "act_horizon": profile["act_horizon"],
                    "prediction_duration_s": profile["pred_horizon"] * .01,
                    "open_loop_duration_s": profile["act_horizon"] * .01,
                    "replanning_hz": 1 / (profile["act_horizon"] * .01),
                    "normalization": {"observation": "train-only mean/std z-score",
                                     "action": "train-only per-dimension q01-q99 to [-1,1], clipped"},
                    "inference_steps": 10, "device": "cuda", "precision": "float32",
                    "seed": SEED, "batch_size": batch_size, "batch_size_attempts": batch_attempts,
                    "epoch_budget": EPOCHS, "steps_per_epoch": steps_per_epoch,
                    "actor_iters": actor_iters, "optimizer": "AdamW",
                    "learning_rate": 1e-4, "weight_decay": 1e-6,
                    "dataloader": {"shuffle": True, "drop_last": True, "num_workers": 0,
                                   "generator_seed": SEED}},
        "resolved_config_path": str(resolved_path),
        "resolved_config_file_sha256": sha(resolved_path),
        "resolved_config_sha256": config_sha,
        "dataset_manifest_sha256": manifest_sha,
        "feature_contract_identity": identities["feature_contract_identity"],
        "action_contract_identity": identities["action_contract_identity"],
        "identities": identities,
        "normalization_fit_source": "selected train trajectories only",
        "training_state_statistics": state_stats,
        "training_action_statistics": action_stats,
        "checkpoint_selection": "minimum validation loss; exact tie selects earlier step",
        "validation_schedule": [0, 1000, actor_iters],
        "train_loss_interval": 100,
        "no_cross_provider_evaluation": True,
    }
    spec_path = profile["training_root"] / "training_spec.yaml"
    write_yaml_new(spec_path, training_spec)
    lock = {"schema": "p1_6-flow-search-training-lock-v0", "sha256": sha(spec_path),
            "resolved_config_sha256": config_sha, "dataset_manifest_sha256": manifest_sha,
            "locked_before_governed_training": True}
    write_new(spec_path.with_name("training_spec_lock.json"), lock)
    write_new(root / "preflight.json", {"pass": True, "dataset_manifest_sha256": manifest_sha,
                "train_samples": len(train_ds), "validation_samples": len(val_ds),
                "train_statistics": train_ds.statistics, "validation_statistics": val_ds.statistics,
                "batch_preflight": batch_attempts, "selected_batch_size": batch_size,
                "steps_per_epoch": steps_per_epoch, "actor_iters": actor_iters,
                "resolved_config_sha256": config_sha})
    write_new(root / "provenance.json", {"variant": name,
                "source_baseline_commit": training_spec["baseline_commit"],
                "dataset_manifest_sha256": manifest_sha,
                "task_artifact_identity": manifest["identities"]["task_artifact"],
                "execution_backend": manifest["execution_backend"],
                "lower_layer_contracts_unchanged": True,
                "qualification_claim": False})
    return {"variant": name, "root": str(root), "train_samples": len(train_ds),
            "validation_samples": len(val_ds), "batch_size": batch_size,
            "steps_per_epoch": steps_per_epoch, "actor_iters": actor_iters,
            "resolved_config_sha256": config_sha, "dataset_manifest_sha256": manifest_sha}


def train(name):
    profile = _variant(name)
    root = profile["root"]
    train_root = profile["training_root"]
    spec_path = train_root / "training_spec.yaml"
    lock = json.loads(spec_path.with_name("training_spec_lock.json").read_text())
    if sha(spec_path) != lock["sha256"]:
        raise ValueError("training specification lock mismatch")
    spec = yaml.safe_load(spec_path.read_text())
    _, manifest_sha = _verify_dataset()
    if manifest_sha != spec["dataset_manifest_sha256"] or sha(root / "resolved_config.yaml") != spec["resolved_config_file_sha256"]:
        raise ValueError("policy_search_dataset_identity: frozen inputs changed after lock")
    if (train_root / "training_summary.json").exists() or (train_root / "metrics_run").exists():
        raise FileExistsError("training already started; refusing to overwrite immutable variant")
    train_ds = Flow100Dataset(MANIFEST, "train", pred_horizon=profile["pred_horizon"],
                              excluded_fields=profile["excluded_fields"])
    val_ds = Flow100Dataset(MANIFEST, "validation", pred_horizon=profile["pred_horizon"],
                            excluded_fields=profile["excluded_fields"])
    _seed_all()
    batch_size = int(spec["learner"]["batch_size"])
    generator = torch.Generator(device="cpu").manual_seed(SEED)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                              drop_last=True, num_workers=0, generator=generator)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                            drop_last=False, num_workers=0)
    if len(train_loader) != int(spec["learner"]["steps_per_epoch"]):
        raise ValueError("selected training loader length differs from frozen budget")
    cfg = baseline.load_variant_config(root / "resolved_config.yaml")
    cfg.agent_sp.artifact_identity = {
        "resolved_config_sha256": spec["resolved_config_sha256"],
        "dataset_manifest_sha256": manifest_sha,
        "agent_type": profile["agent_type"],
        "feature_contract_identity": spec["feature_contract_identity"],
        "action_contract_identity": spec["action_contract_identity"],
    }
    if config_identity(cfg) != spec["resolved_config_sha256"]:
        raise ValueError("resolved config semantic identity mismatch")
    agent = make_agent(profile["agent_type"], cfg)
    if next(agent.actor.parameters()).device.type != "cuda":
        raise ValueError("Flow actor did not initialize on CUDA")
    if sum(p.numel() for p in agent.actor.parameters()) != 19512264:
        raise ValueError("Flow actor parameter count differs from V0")
    optimizer = agent.actor_optimizer.param_groups[0]
    if (not isinstance(agent.actor_optimizer, torch.optim.AdamW)
            or optimizer["lr"] != 1e-4 or optimizer["weight_decay"] != 1e-6):
        raise ValueError("optimizer differs from frozen Flow profile")
    states = train_ds.get_all_states().float().to(agent.device)
    actions = train_ds.get_all_actions().float().to(agent.device)
    agent.fit_obs_normalizer(states)
    agent.fit_action_normalizer(actions)
    if (not torch.allclose(agent.obs_normalizer.mean.detach().cpu(), states.mean(0).cpu())
            or not torch.allclose(agent.obs_normalizer.std.detach().cpu(), states.std(0).cpu())
            or not torch.allclose(agent.action_normalizer.low_val.detach().cpu(), torch.quantile(actions.cpu(), .01, dim=0))
            or not torch.allclose(agent.action_normalizer.high_val.detach().cpu(), torch.quantile(actions.cpu(), .99, dim=0))):
        raise ValueError("normalizers are not fitted from selected train corpus")
    normalizer_state = _normalizer_state(agent)
    normalizer_identity = digest(_normalizer_json(normalizer_state))
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    checkpoints = train_root / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=False)
    candidates = []

    def save_candidate(current, row):
        step = int(row["step"])
        path = checkpoints / f"validation_step_{step:04d}.pth"
        current.save(str(path), meta={"purpose": "policy_search_validation_candidate",
                                      "variant": name, "step": step,
                                      "validation_loss": float(row["loss"]),
                                      "normalizer_identity": normalizer_identity,
                                      "resolved_config_sha256": spec["resolved_config_sha256"],
                                      "dataset_manifest_sha256": manifest_sha})
        candidates.append({"step": step, "loss": float(row["loss"]),
                           "samples": int(row["samples"]), "batches": int(row["batches"]),
                           "path": str(path)})

    n_steps = int(spec["learner"]["actor_iters"])
    started = time.monotonic()
    result = agent.train_loop(train_loader, n_steps, save_dir=str(train_root / "metrics_run"),
                              validation_loader=val_loader, validation_callback=save_candidate)
    torch.cuda.synchronize()
    wall_s = time.monotonic() - started
    if agent.step != n_steps:
        raise ValueError(f"optimizer update count mismatch: {agent.step}/{n_steps}")
    if [x["step"] for x in candidates] != [0, 1000, n_steps]:
        raise ValueError(f"validation schedule mismatch: {[x['step'] for x in candidates]}")
    metrics_path = train_root / "metrics_run" / "training_metrics.jsonl"
    rows = [json.loads(line) for line in metrics_path.read_text().splitlines() if line.strip()]
    train_rows = [r for r in rows if r["kind"] == "train"]
    validation_rows = [r for r in rows if r["kind"] == "validation"]
    expected_train_steps = list(range(100, n_steps + 1, 100))
    if n_steps % 100:
        expected_train_steps.append(n_steps)
    if [r["step"] for r in train_rows] != expected_train_steps:
        raise ValueError("train metric interval mismatch")
    if not all(np.isfinite(float(r["loss"])) for r in train_rows + validation_rows):
        raise ValueError("flow_training_numerics: non-finite training/validation loss")
    best = min(candidates, key=lambda r: (r["loss"], r["step"]))
    best_path = checkpoints / "best_validation.pth"
    shutil.copy2(best["path"], best_path)
    final_path = checkpoints / f"final_step{n_steps}.pth"
    agent.save(str(final_path), meta={"purpose": "policy_search_final_checkpoint",
                                      "variant": name, "optimizer_step": n_steps,
                                      "epoch_equivalent": EPOCHS,
                                      "normalizer_identity": normalizer_identity,
                                      "resolved_config_sha256": spec["resolved_config_sha256"],
                                      "dataset_manifest_sha256": manifest_sha})
    gpu = torch.cuda.get_device_properties(torch.cuda.current_device())
    summary = {
        "schema": "p1_6-policy-search-flow-training-summary-v0",
        "variant": name,
        "total_optimizer_steps": n_steps,
        "epoch_budget": EPOCHS,
        "effective_epochs": n_steps / len(train_loader),
        "steps_per_epoch": len(train_loader),
        "batch_size": batch_size,
        "train_samples": len(train_ds),
        "validation_samples": len(val_ds),
        "initial_train_loss": train_rows[0]["loss"],
        "final_train_loss": train_rows[-1]["loss"],
        "minimum_train_window_loss": min(float(r["loss"]) for r in train_rows),
        "initial_validation_loss": validation_rows[0]["loss"],
        "step1000_validation_loss": next(r["loss"] for r in validation_rows if r["step"] == 1000),
        "final_validation_loss": validation_rows[-1]["loss"],
        "minimum_validation_loss": best["loss"],
        "best_validation_step": best["step"],
        "validation_rows": validation_rows,
        "train_curve_rows": train_rows,
        "training_wall_time_s": wall_s,
        "gpu": gpu.name,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "precision": "float32",
        "peak_cuda_memory_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "peak_cuda_memory_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        "parameter_count": sum(p.numel() for p in agent.actor.parameters()),
        "normalizer_identity": normalizer_identity,
        "normalizer_statistics": _normalizer_json(normalizer_state),
        "resolved_config_sha256": spec["resolved_config_sha256"],
        "dataset_manifest_sha256": manifest_sha,
        "training_spec_sha256": lock["sha256"],
        "best_checkpoint_sha256": sha(best_path),
        "final_checkpoint_sha256": sha(final_path),
        "training_loop_summary": result,
    }
    write_new(train_root / "training_summary.json", summary)
    write_new(checkpoints / "checkpoint_manifest.json", {
        "schema": "p1_6-policy-search-checkpoints-v0",
        "selection": "minimum validation loss; earlier step wins exact ties",
        "validation_candidates": candidates,
        "checkpoints": [
            {"file": str(p), "sha256": sha(p), "step": step,
             "epoch_equivalent": step / len(train_loader),
             "validation_loss": val_loss,
             "resolved_config_sha256": spec["resolved_config_sha256"],
             "dataset_manifest_sha256": manifest_sha,
             "feature_contract_identity": spec["feature_contract_identity"],
             "action_contract_identity": spec["action_contract_identity"],
             "normalizer_identity": normalizer_identity}
            for p, step, val_loss in ((best_path, best["step"], best["loss"]),
                                      (final_path, n_steps, validation_rows[-1]["loss"]))
        ],
    })
    return summary


def lock_rollout(name):
    """Freeze the six-seed CUDA-synchronous rollout before any episode runs."""
    from task_env.diagnostics.phase1.policy_search.timebase100 import context, sample_for_variant

    profile = _variant(name)
    root = profile["root"]
    train_root = profile["training_root"]
    spec = yaml.safe_load((train_root / "training_spec.yaml").read_text())
    summary = json.loads((train_root / "training_summary.json").read_text())
    checkpoint = train_root / "checkpoints" / "best_validation.pth"
    if not checkpoint.is_file() or sha(checkpoint) != summary["best_checkpoint_sha256"]:
        raise ValueError("best-validation checkpoint identity mismatch")
    _, artifact, _, _, _, _ = context("cuda")
    seeds = [1000, 1010, 1020, 1040, 1050, 1100]
    samples = {}
    for seed in seeds:
        sample = sample_for_variant(artifact, seed)
        samples[str(seed)] = sample.to_mapping()
    rollout = {
        "schema": "p1_6-100hz-policy-search-rollout-spec-v0",
        "variant": name,
        "provider": "geophys",
        "physics_backend": "cuda",
        "policy_device": "cuda",
        "synchronous_inference_simulator_frozen": True,
        "task_artifact_sha256": artifact.identity_hash,
        "dataset_manifest_sha256": spec["dataset_manifest_sha256"],
        "resolved_config_sha256": spec["resolved_config_sha256"],
        "best_checkpoint_path": str(checkpoint),
        "best_checkpoint_sha256": sha(checkpoint),
        "cohort_seeds": seeds,
        "policy_rng_rule": "100000 + task_seed; one inference sampling realization per episode",
        "success_gate": "cube_lift >= 0.10 m",
        "max_control_steps": 2500,
        "obs_horizon": 2,
        "pred_horizon": profile["pred_horizon"],
        "act_horizon": profile["act_horizon"],
        "observation_contract": spec["learner"]["observation_contract"],
        "reset_samples": samples,
        "no_expert_fallback": True,
    }
    path = root / "rollout_spec.yaml"
    write_yaml_new(path, rollout)
    lock = {"schema": "p1_6-flow-search-rollout-lock-v0", "sha256": sha(path),
            "checkpoint_sha256": rollout["best_checkpoint_sha256"],
            "locked_before_first_rollout": True}
    write_new(root / "rollout_spec_lock.json", lock)
    return {"rollout_spec_sha256": lock["sha256"], "best_checkpoint_sha256": sha(checkpoint),
            "seeds": seeds, "reset_sample_hashes": {
                seed: sample_for_variant(artifact, seed).identity_hash for seed in seeds}}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=tuple(VARIANTS), required=True)
    parser.add_argument("--stage", choices=("prepare", "train", "lock-rollout"), required=True)
    args = parser.parse_args()
    if args.stage == "prepare":
        result = prepare(args.variant)
    elif args.stage == "train":
        result = train(args.variant)
    else:
        result = lock_rollout(args.variant)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
