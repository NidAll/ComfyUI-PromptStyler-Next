# Local-only custom packs for ComfyUI

Shipped inventory packs live in `promptstyler_next/packs/`. Use this directory for personal or otherwise unbundled version-1 JSON packs; keep private packs out of Git. Place `.json` files here and restart ComfyUI. Packs are validated once when the nodes initialize; invalid or duplicate definitions fail visibly. Only regular `.json` files are read. Symlinks are refused. Node inputs cannot select filesystem paths. See `docs/packs.md` and `docs/style-library.md` for the pack contract and inventory.
