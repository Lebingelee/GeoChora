"""Composable initial-state capabilities for selected RuntimeSession owners."""
from dataclasses import dataclass

from ...environment.reference_binding import validate_initial_state_publication


@dataclass(frozen=True)
class InitialStateResult:
    typed_publication: object | None = None
    feedback: object | None = None
    materialization_receipt: object | None = None
    publishes_position: bool = False


@dataclass(frozen=True)
class PositionInitialState:
    declaration: object
    scene: object
    joint_bindings: object
    frame_bindings: object
    controllers: tuple
    control_plan: object
    failure_phase: str = 'snapshot_readback'
    supports_stop: bool = True

    def initialize(self, session, state):
        publication = session.snapshot_v1(scene=self.scene, joint_bindings=self.joint_bindings,
            frame_bindings=self.frame_bindings, requirements=self.declaration.position_state_requirements())
        validate_initial_state_publication(session, publication, state)
        for capability in self.controllers:
            capability.initialize(publication, self.control_plan)
        return InitialStateResult(publication, None,
            self.declaration.initial_materialization_receipt(session), True)


@dataclass(frozen=True)
class PhysicalInitialState:
    execution: object
    publish_typed: bool
    supports_stop: bool
    failure_phase: str = 'snapshot_readback'

    def initialize(self, session, state):
        execution = self.execution
        publication = session.snapshot_v2(scene=execution.scene, joint_bindings=execution.joint_bindings,
            frame_bindings=execution.frame_bindings, requirements=execution.requirements)
        validate_initial_state_publication(session, publication, state)
        execution.initialize_controllers(session, publication)
        return InitialStateResult(publication if self.publish_typed else None)


@dataclass(frozen=True)
class MixedInitialState:
    controller: object
    failure_phase: str = 'snapshot_readback'

    def initialize(self, _session, state):
        self.controller.reset(state)
        return InitialStateResult()


@dataclass(frozen=True)
class LegacyFeedbackInitialState:
    controller: object
    failure_phase: str = 'controller_feedback'

    def initialize(self, session, state):
        feedback = session.control_feedback(state)
        self.controller.reset(state, feedback)
        return InitialStateResult(feedback=feedback)
