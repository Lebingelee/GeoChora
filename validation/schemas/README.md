# Supported task schemas

`low-detail-task-1.1.0.schema.json` is the unchanged SimDataKit authored low-detail
task contract at commit `20e9b732252659eea69deca9184f8185ae5a0f52`, source path
`src/simdatakit/schemas/low-detail-authored-task.schema.json`.
SHA-256: `7bd049005f4a7de1104579193326ffa91580ac8fe58b51aa121ecf0b960d6f86`.
The local [.gitattributes](.gitattributes) preserves these upstream bytes in Git and across checkouts.
All references are local to this document. Offline consumers need no SimDataKit checkout.

`low-detail-task-1.2.0.schema.json` is a byte-for-byte copy of the SimDataKit authored
low-detail task contract from the working tree at base commit
`20e9b732252659eea69deca9184f8185ae5a0f52`, source path
`src/simdatakit/schemas/low-detail-authored-task-1.2.0.schema.json`.
SHA-256: `4ccb0a21592e0c7f88bfe2f349c9b54430006f3c72c6ec5d407d0f6f68e011d8`.
The schema requires `truth.group` and `truth.goal` and allows `truth.bind` and
`truth.process`.

`validation.inputs.validate_task` and `load_task` enforce each declared version and preserve
the original record. This input check does not grant dataset publication status,
interpret task meaning, or judge physical task completion. Other task versions
require explicit support; the lower-level source-review protocol remains separate.
