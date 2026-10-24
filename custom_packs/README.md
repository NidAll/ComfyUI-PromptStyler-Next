# Custom packs for ComfyUI

Place version-1 JSON style packs directly in this directory and restart ComfyUI. Packs are validated once when the nodes initialize; invalid or duplicate definitions fail visibly. Only `.json` regular files are read. Symlinks are refused. Node inputs cannot select filesystem paths. Keep private packs out of Git. See `docs/style-library.md` for the pack contract.
