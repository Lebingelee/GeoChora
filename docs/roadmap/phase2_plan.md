# Phase II handoff plan

Phase II inherits the public contracts and source baseline recorded by GeoChora v1.0. The release tag remains immutable. At bootstrap, develop starts from the same release commit as main; subsequent Phase II work proceeds on develop and topic branches. Main remains the release line. Do not copy Core contracts into a second actively maintained tree.

This is a handoff plan, not an approved feature schedule. It does not claim PhysPi integration, OpenUSD workflows, real-to-sim pipelines, or new task/provider qualifications as implemented.

## Questions for Phase II research

- How should Core contracts express more task families while preserving provider-neutral action, observation, reset, and lifecycle semantics?
- Which visual observation and visuomotor intersections can be qualified under the deferred P1.7 route?
- What provider/runtime metadata and recorder or replay oracles are needed for reproducible comparisons?
- Which bounded provider intersections should be qualified next, and which unsupported intersections should remain fail-closed?
- How can task artifacts, experiments, evaluation reports, Human decisions, and evidence remain separately identifiable as the project grows?

P1.7 and P1.8 follow-ups may proceed alongside this work. A Phase II proposal becomes an implementation commitment only after its owner, supported intersection, evidence plan, and review gate are accepted.
