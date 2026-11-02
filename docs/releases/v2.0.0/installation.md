# v2.0.0 source setup notes

Use the exact source tag `refs/tags/v2.0.0`. The repository has no root packaging metadata; the tagged tree's own dependency declarations and setup notes are authoritative for that version. Do not apply the v2.1 candidate's installation instructions as a guarantee for this snapshot.

The tag pins GeoPhys at `a53a8cfed7c9d6464274b5c96fca601271dc4ee4` and MuJoCo Menagerie at `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`. A submodule pin identifies source; it is not a bundled asset archive or license grant. Obtain simulator installations and third-party assets separately under their applicable upstream terms.

This source record does not validate a new machine, OS, Python environment, simulator version, or task/provider route.
