from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import torch
import torch.nn as nn


class Pi0DependencyError(ImportError):
    """Raised when LeRobot/pi0 dependencies are needed but unavailable."""


PI0_NORMALIZATION_SOURCE_LEROBOT = "lerobot"
PI0_NORMALIZATION_SOURCE_NONE = "none"
PI0_NORMALIZATION_SOURCE_AGENT_FACTORY = "agent_factory"
PI0_NORMALIZATION_SOURCES = {
    PI0_NORMALIZATION_SOURCE_LEROBOT,
    PI0_NORMALIZATION_SOURCE_NONE,
    PI0_NORMALIZATION_SOURCE_AGENT_FACTORY,
}
PI0_STATE_KEY = "observation.state"
PI0_ACTION_KEY = "action"
PI0_TASK_KEY = "task"
PI0_IMAGE_PREFIX = "observation.images."
PI0_PREPROCESSOR_NAME = "policy_preprocessor.json"
PI0_POSTPROCESSOR_NAME = "policy_postprocessor.json"


def _cfg_get(cfg: Any, key: str, default: Any = None) -> Any:
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    return getattr(cfg, key, default)


def _resolve_pretrained_path(cfg: Any) -> str:
    pretrained_path = str(_cfg_get(cfg, "pretrained_path", "") or _cfg_get(cfg, "checkpoint_path", "")).strip()
    if not pretrained_path:
        raise ValueError(
            "Pi0ActorConfig requires actor.pretrained_path or actor.checkpoint_path "
            "when actor.mock_mode=False."
        )
    return pretrained_path


def _looks_like_local_path(path: str) -> bool:
    return path.startswith(("/", ".", "~")) or Path(path).exists()


def _validate_pretrained_dir(pretrained_path: str, *, local_files_only: bool) -> None:
    if not local_files_only and not _looks_like_local_path(pretrained_path):
        return
    path = Path(pretrained_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(
            "pi0 pretrained_model directory does not exist: "
            f"{pretrained_path}. Point actor.pretrained_path at "
            "checkpoints/<step>/pretrained_model/."
        )
    if not path.is_dir():
        raise ValueError(
            "pi0 actor.pretrained_path must point at a LeRobot pretrained_model directory, "
            f"not a single file: {pretrained_path}."
        )
    missing = [
        filename
        for filename in ("config.json", "model.safetensors", PI0_PREPROCESSOR_NAME, PI0_POSTPROCESSOR_NAME)
        if not (path / filename).exists()
    ]
    if missing:
        raise FileNotFoundError(
            "pi0 pretrained_model directory is missing required LeRobot v5 files "
            f"{missing} under {pretrained_path}."
        )


def resolve_pi0_normalization_source(cfg: Any) -> str:
    source = str(_cfg_get(cfg, "normalization_source", PI0_NORMALIZATION_SOURCE_LEROBOT) or "").strip().lower()
    if source not in PI0_NORMALIZATION_SOURCES:
        raise ValueError(
            "Pi0ActorConfig.normalization_source must be one of "
            f"{sorted(PI0_NORMALIZATION_SOURCES)}, got {source!r}."
        )
    if source == PI0_NORMALIZATION_SOURCE_AGENT_FACTORY:
        raise ValueError(
            "pi0 does not support agent_factory action normalization in phase B. "
            "Use actor.normalization_source='lerobot' so LeRobot PI0Policy owns action stats, "
            "or actor.normalization_source='none' only for mock/debug paths."
        )
    if source == PI0_NORMALIZATION_SOURCE_NONE and not bool(_cfg_get(cfg, "mock_mode", True)):
        raise ValueError(
            "actor.normalization_source='none' is only supported with actor.mock_mode=True. "
            "Loaded pi0 checkpoints should use LeRobot preprocess/postprocess via "
            "actor.normalization_source='lerobot'."
        )
    return source


def _to_tensor(value: Any) -> torch.Tensor:
    if isinstance(value, torch.Tensor):
        return value
    return torch.as_tensor(value)


def _as_batched_state(value: Any, *, single_prompt: bool = False) -> torch.Tensor:
    state = _to_tensor(value).float()
    if state.ndim == 1:
        return state.unsqueeze(0)
    if state.ndim == 2:
        if single_prompt and state.shape[0] != 1:
            return state[-1:].contiguous()
        return state
    if state.ndim == 3:
        return state[:, -1, :]
    raise ValueError(f"pi0 state must have shape [D], [B,D], or [B,T,D], got {tuple(state.shape)}.")


def _as_batched_image(value: Any, *, batch_size: Optional[int] = None) -> torch.Tensor:
    image = _to_tensor(value)
    if image.dtype == torch.uint8:
        image = image.float() / 255.0
    else:
        image = image.float()

    if image.ndim == 5:
        image = image[:, -1]
    elif image.ndim == 4 and batch_size == 1 and image.shape[0] != 1 and (image.shape[1] == 3 or image.shape[-1] == 3):
        image = image[-1]
    elif image.ndim == 4 and image.shape[-1] != 3 and image.shape[1] != 3:
        image = image[-1]
    if image.ndim == 3:
        image = image.unsqueeze(0)
    if image.ndim != 4:
        raise ValueError(
            "pi0 image observations must have shape [C,H,W], [H,W,C], [B,C,H,W], or [B,H,W,C], "
            f"got {tuple(image.shape)}."
        )
    if image.shape[1] != 3 and image.shape[-1] != 3:
        raise ValueError(
            "pi0 image observations must keep an explicit RGB channel dimension of size 3; "
            f"got {tuple(image.shape)}."
        )
    return image


def _to_device_batch(batch: Dict[str, Any], device: torch.device) -> Dict[str, Any]:
    moved: Dict[str, Any] = {}
    for key, value in batch.items():
        if isinstance(value, torch.Tensor):
            moved[key] = value.to(device)
        else:
            moved[key] = value
    return moved


def _coerce_task(prompt: Optional[Any], batch_size: int) -> Any:
    if prompt is None:
        raise ValueError("pi0 observations require a prompt/task string.")
    if isinstance(prompt, str):
        return prompt if batch_size == 1 else [prompt for _ in range(batch_size)]
    if isinstance(prompt, Sequence) and not isinstance(prompt, (bytes, bytearray)):
        values = list(prompt)
        if len(values) != batch_size:
            raise ValueError(f"pi0 prompt list length {len(values)} does not match batch size {batch_size}.")
        return values
    return prompt


def _lerobot_image_keys(obs: Dict[str, Any]) -> list[str]:
    return sorted(str(key) for key in obs.keys() if str(key).startswith(PI0_IMAGE_PREFIX))


def build_pi0_lerobot_batch(
    obs: Dict[str, Any],
    *,
    prompt: Optional[Any] = None,
    image_keys: Optional[Sequence[str]] = None,
    prompt_key: str = "prompt",
    state_key: str = PI0_STATE_KEY,
) -> Dict[str, Any]:
    """
    Convert a minimally structured agent_factory observation to LeRobot pi0 keys.

    Supported inputs:
    - Already-LeRobot obs with ``observation.state`` and ``observation.images.<camera>``.
    - agent_factory obs with ``state`` plus ``images`` or ``rgb`` as a camera-name dict.

    A concatenated ``rgb`` tensor is intentionally rejected because pi0 needs
    stable per-camera keys.
    """

    if "lerobot_batch" in obs:
        nested = obs["lerobot_batch"]
        if not isinstance(nested, dict):
            raise TypeError("obs['lerobot_batch'] must be a dict.")
        return build_pi0_lerobot_batch(
            nested,
            prompt=prompt,
            image_keys=image_keys,
            prompt_key=prompt_key,
            state_key=state_key,
        )

    raw_prompt = prompt if prompt is not None else obs.get(PI0_TASK_KEY, obs.get(prompt_key, None))
    single_prompt = isinstance(raw_prompt, str)

    batch: Dict[str, Any] = {}
    source_state_key = state_key if state_key in obs else PI0_STATE_KEY if PI0_STATE_KEY in obs else "state"
    if source_state_key not in obs:
        raise KeyError(
            "pi0 observations require 'observation.state' or 'state'. "
            "Do not pass only visual observations."
        )
    batch[PI0_STATE_KEY] = _as_batched_state(obs[source_state_key], single_prompt=single_prompt)
    batch_size = int(batch[PI0_STATE_KEY].shape[0])

    existing_image_keys = _lerobot_image_keys(obs)
    if existing_image_keys:
        selected_keys = [f"{PI0_IMAGE_PREFIX}{key}" for key in image_keys or []]
        selected_keys = selected_keys or existing_image_keys
        missing = [key for key in selected_keys if key not in obs]
        if missing:
            raise KeyError(f"pi0 observation is missing image keys: {missing}")
        for key in selected_keys:
            image = _as_batched_image(obs[key], batch_size=batch_size)
            if int(image.shape[0]) != batch_size:
                raise ValueError(f"{key} batch size {image.shape[0]} does not match state batch size {batch_size}.")
            batch[key] = image
    else:
        image_source = None
        if "images" in obs:
            image_source = obs["images"]
        elif "rgb" in obs:
            image_source = obs["rgb"]

        if not isinstance(image_source, dict):
            raise ValueError(
                "pi0 requires multi-view images as a camera-name dict or LeRobot "
                "'observation.images.<camera>' keys. A channel-concatenated obs['rgb'] tensor "
                "cannot be safely split for pi0."
            )

        camera_names = list(image_keys or image_source.keys())
        if not camera_names:
            raise ValueError("pi0 observations require at least one camera image.")
        for camera_name in camera_names:
            if camera_name not in image_source:
                raise KeyError(f"pi0 image source is missing camera {camera_name!r}.")
            key = f"{PI0_IMAGE_PREFIX}{camera_name}"
            image = _as_batched_image(image_source[camera_name], batch_size=batch_size)
            if int(image.shape[0]) != batch_size:
                raise ValueError(f"{key} batch size {image.shape[0]} does not match state batch size {batch_size}.")
            batch[key] = image

    batch[PI0_TASK_KEY] = _coerce_task(raw_prompt, batch_size)
    return batch


class Pi0PolicyWrapper(nn.Module):
    """
    Thin adapter around LeRobot PI0Policy.

    The first implementation intentionally keeps training out of agent_factory:
    LeRobotDataset + lerobot-train owns full fine-tuning. This wrapper is for
    checkpoint loading, rollout inference, and later action-head feature hooks.
    """

    def __init__(
        self,
        cfg: Any,
        action_dim: int,
        pred_horizon: int,
    ):
        super().__init__()
        self.cfg = cfg
        self.action_dim = int(action_dim)
        self.pred_horizon = int(pred_horizon)
        self.feature_dim = int(_cfg_get(cfg, "feature_dim", 1024))
        self.mock_mode = bool(_cfg_get(cfg, "mock_mode", True))
        self.normalization_source = resolve_pi0_normalization_source(cfg)
        self.image_keys = list(_cfg_get(cfg, "image_keys", []) or [])
        self.pretrained_path = "" if self.mock_mode else _resolve_pretrained_path(cfg)
        self.policy = None
        self.preprocessor = None
        self.postprocessor = None
        self._processor_device: Optional[str] = None
        self.register_buffer("_device_anchor", torch.empty(0), persistent=False)

        if not self.mock_mode:
            self.policy = self._load_lerobot_policy()

    @property
    def device(self) -> torch.device:
        return self._device_anchor.device

    def _load_lerobot_policy(self):
        try:
            from lerobot.policies.pi0.modeling_pi0 import PI0Policy
        except ImportError as exc:
            raise Pi0DependencyError(
                "Pi0PolicyWrapper requires LeRobot with pi0 support. "
                "Install the Python 3.12 pi0 stack from requirements-py312.txt "
                "or enable actor.mock_mode for local smoke tests."
            ) from exc

        local_files_only = bool(_cfg_get(self.cfg, "local_files_only", True))
        _validate_pretrained_dir(self.pretrained_path, local_files_only=local_files_only)

        return PI0Policy.from_pretrained(
            self.pretrained_path,
            revision=_cfg_get(self.cfg, "pretrained_revision", None),
            local_files_only=local_files_only,
        )

    def _ensure_lerobot_processors(self) -> None:
        if self.mock_mode:
            return
        device_name = str(self.device)
        if self.preprocessor is not None and self.postprocessor is not None and self._processor_device == device_name:
            return
        try:
            from lerobot.policies.factory import make_pre_post_processors
        except ImportError as exc:
            raise Pi0DependencyError(
                "Pi0PolicyWrapper requires LeRobot v5 policy processors for real pi0 inference. "
                "Install the Python 3.12 pi0 stack from requirements-py312.txt."
            ) from exc

        if self.policy is None:
            raise RuntimeError("Pi0PolicyWrapper policy is not loaded.")
        self.policy.to(self.device)
        device_override = {"device": device_name}
        try:
            self.preprocessor, self.postprocessor = make_pre_post_processors(
                self.policy.config,
                pretrained_path=self.pretrained_path,
                pretrained_revision=_cfg_get(self.cfg, "pretrained_revision", None),
                preprocessor_overrides={"device_processor": device_override},
                postprocessor_overrides={"device_processor": {"device": "cpu"}},
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to load LeRobot v5 pi0 policy_preprocessor/policy_postprocessor "
                f"from {self.pretrained_path!r}. Use the full checkpoints/<step>/pretrained_model/ "
                "directory produced by lerobot-train."
            ) from exc
        self._processor_device = device_name

    def _infer_batch_size(self, obs: Any) -> int:
        if isinstance(obs, torch.Tensor):
            return int(obs.shape[0]) if obs.ndim > 0 else 1
        if isinstance(obs, dict):
            for value in obs.values():
                try:
                    return self._infer_batch_size(value)
                except ValueError:
                    continue
        raise ValueError("Unable to infer batch size from obs for pi0 mock inference.")

    def preprocess_agent_factory_obs(self, obs: Dict[str, Any], prompt: Optional[Any] = None) -> Dict[str, Any]:
        """
        Convert runner/dataset observations into the raw LeRobot pi0 batch
        shape. This keeps multi-view images under separate
        ``observation.images.<camera>`` keys.
        """

        batch = build_pi0_lerobot_batch(
            obs,
            prompt=prompt,
            image_keys=self.image_keys,
            prompt_key=str(_cfg_get(self.cfg, "prompt_key", "prompt")),
            state_key=str(_cfg_get(self.cfg, "state_key", PI0_STATE_KEY)),
        )
        return _to_device_batch(batch, self.device)

    def _preprocess_for_policy(self, obs: Dict[str, Any], prompt: Optional[Any] = None) -> Dict[str, Any]:
        batch = self.preprocess_agent_factory_obs(obs, prompt=prompt)
        self._ensure_lerobot_processors()
        if self.preprocessor is None:
            return batch
        return self.preprocessor(batch)

    def _postprocess_action_chunk(self, action_chunk: torch.Tensor) -> torch.Tensor:
        if self.postprocessor is None:
            return action_chunk
        if action_chunk.ndim != 3:
            raise ValueError(f"pi0 policy action chunk must have shape [B,T,D], got {tuple(action_chunk.shape)}.")
        processed_actions = []
        for horizon_idx in range(int(action_chunk.shape[1])):
            single_action = action_chunk[:, horizon_idx, :]
            processed_actions.append(self.postprocessor(single_action))
        return torch.stack(processed_actions, dim=1)

    def _align_action_chunk(self, action_chunk: torch.Tensor) -> torch.Tensor:
        if action_chunk.ndim == 2:
            action_chunk = action_chunk[:, None, :]
        if action_chunk.ndim != 3:
            raise ValueError(f"pi0 sample_action must return [B,T,D], got {tuple(action_chunk.shape)}.")

        action_chunk = action_chunk.to(device=self.device, dtype=torch.float32)
        if int(action_chunk.shape[-1]) < self.action_dim:
            pad = torch.zeros(
                (*action_chunk.shape[:-1], self.action_dim - int(action_chunk.shape[-1])),
                dtype=action_chunk.dtype,
                device=action_chunk.device,
            )
            action_chunk = torch.cat([action_chunk, pad], dim=-1)
        elif int(action_chunk.shape[-1]) > self.action_dim:
            if bool(_cfg_get(self.cfg, "require_env_action_dim_match", True)):
                raise ValueError(
                    "pi0 action dimension does not match env action_dim: "
                    f"policy returned {action_chunk.shape[-1]}, env expects {self.action_dim}."
                )
            action_chunk = action_chunk[..., : self.action_dim]

        horizon = int(action_chunk.shape[1])
        if horizon < self.pred_horizon:
            repeat = action_chunk[:, -1:, :].expand(-1, self.pred_horizon - horizon, -1)
            action_chunk = torch.cat([action_chunk, repeat], dim=1)
        elif horizon > self.pred_horizon:
            action_chunk = action_chunk[:, : self.pred_horizon, :]
        return action_chunk

    @torch.no_grad()
    def sample_action(self, obs: Dict[str, Any], prompt: Optional[Any] = None, **kwargs) -> torch.Tensor:
        if self.mock_mode:
            try:
                batch_size = int(self.preprocess_agent_factory_obs(obs, prompt=prompt)[PI0_STATE_KEY].shape[0])
            except Exception:
                batch_size = self._infer_batch_size(obs)
            # Mock pi0 follows the same external contract as real pi0: returned
            # actions are env-native and are not post-processed by agent_factory.
            return torch.zeros(
                (batch_size, self.pred_horizon, self.action_dim),
                dtype=torch.float32,
                device=self.device,
            )

        batch = self._preprocess_for_policy(obs, prompt=prompt)
        if hasattr(self.policy, "predict_action_chunk"):
            action_chunk = self.policy.predict_action_chunk(
                batch,
                **{
                    key: value
                    for key, value in kwargs.items()
                    if key in {"inference_delay", "prev_chunk_left_over", "execution_horizon"}
                },
            )
        else:
            action = self.policy.select_action(batch)
            action_chunk = action[:, None, :].expand(-1, self.pred_horizon, -1)
        action_chunk = self._postprocess_action_chunk(action_chunk)
        return self._align_action_chunk(action_chunk)

    @torch.no_grad()
    def extract_action_head_feature(self, obs: Dict[str, Any], prompt: Optional[Any] = None, **kwargs) -> torch.Tensor:
        if self.mock_mode:
            batch_size = self._infer_batch_size(obs)
            return torch.zeros((batch_size, self.feature_dim), dtype=torch.float32, device=self.device)

        del obs, prompt, kwargs
        raise NotImplementedError(
            "Real pi0 action-head feature extraction will be wired in the feature exporter phase. "
            "The intended hook is the LeRobot PI0 suffix_out tensor immediately before action_out_proj."
        )
