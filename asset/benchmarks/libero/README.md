# LIBERO pilot source bundle

This directory owns a versioned, source-only bundle for the single R07b pilot
`libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate`.
It does not register a Core task, grant redistribution rights, or claim runtime
compatibility.

`source_manifest.json` binds 103 source and notice files to LIBERO
`8f1084e3132a39270c3a13ebe37270a43ece2a01` and robosuite
`fbee5844ff5632f5b5698e204ec5357ca50be0df`. Its active XML-derived asset
closure has 89 files (76,512,539 bytes). Four candidate rows are recorded as
excluded because the selected LIBERO tabletop scene replaces the two floor and
wall texture references, while the Robosuite default table arena is not used.
The manifest lists source logical paths and hashes; it contains no binary
asset payloads or workstation cache paths.

## Local install and independent verify

Use a fresh target and provide source roots whose relative namespaces match the
manifest's `source_root_id` and `source_path`. The paths below are examples;
they are inputs to the local audit command, not runtime configuration:

```sh
python asset/benchmarks/libero/tools/source_bundle.py install \
  --manifest asset/benchmarks/libero/source_manifest.json \
  --target /local/audit/libero-pilot \
  --source-root libero-tree=/path/to/pinned/libero-tree \
  --source-root robosuite-tree=/path/to/pinned/robosuite-tree \
  --source-root libero-readback=/path/to/libero-readback \
  --source-root robosuite-audit=/path/to/robosuite-readback \
  --source-root libero-assets=/path/to/libero-asset-cache \
  --source-root robosuite-assets=/path/to/robosuite-asset-cache
python asset/benchmarks/libero/tools/source_bundle.py verify \
  --manifest asset/benchmarks/libero/source_manifest.json \
  --target /local/audit/libero-pilot \
  --receipt-out /local/audit/libero-pilot.verify.json
```

`install` reads and checks each configured source file before publishing a
receipt. A matching existing target is re-read and returned as
`ALREADY_PRESENT_VERIFIED`; a different manifest, target identity, changed
bytes, extra files, or symlink is rejected. `verify` independently opens every
installed file, checks the exact file/directory set, verifies receipt binding,
and recomputes the XML reference closure. It does not accept the install
producer's status as verification.

The selected `.pruned_init` is stored and hashed as opaque bytes. This tool does
not unpickle it, use `torch.load`, or claim reset realization. Style-derived
texture paths are recorded as explicit source-to-effective mappings, with the
original XML hash preserved.

## Rights boundary

The R07a004 review supports this one pilot for local noncommercial research
simulation. File-level source families, attribution clues, and known record
gaps remain in the manifest and notices. Redistribution, commercial use, and
public bundling are not approved. In particular, the plate model's exact Fuel
item ID and the `martin_novak_wood_table.png` credit remain provenance gaps.
