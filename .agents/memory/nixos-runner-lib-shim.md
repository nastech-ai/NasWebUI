---
name: NixOS GitHub Actions runner lib-shim
description: How to run the GitHub Actions self-hosted runner on Replit's NixOS without library/vdso crashes
---

The runner's bundled .NET 6 needs libstdc++, libicu, and libz — none in PATH on NixOS.

**DO NOT** add full system dirs (e.g. `/lib/x86_64-linux-gnu`) to LD_LIBRARY_PATH — this breaks vdso for every child process (chmod, curl, python3 all crash with "invalid mode for dlopen").

**DO NOT** add Nix glibc to LD_LIBRARY_PATH — causes "stack smashing detected" in runner binary.

**Fix:** Create `actions-runner/lib-shim/` with only the three missing libs symlinked:
- libstdc++.so.6 → /nix/store/*-gcc-*-lib/lib/libstdc++.so.6
- libicuuc.so.76 + libicui18n.so.76 + libicudata.so.76 → /nix/store/*-icu4c-*/lib/
- libz.so.1 → /lib/x86_64-linux-gnu/libz.so.1

Then set LD_LIBRARY_PATH to ONLY that single directory.

**Why:** Targeted shim avoids vdso/glibc conflicts while satisfying .NET 6 deps.

**How to apply:** Use `actions-runner/run-replit.sh` wrapper which sets LD_LIBRARY_PATH before exec'ing run.sh. Runner is registered as "GitHub Actions Runner" Replit workflow.

Nix packages needed: patchelf, glibc (for finding paths), gcc (libstdc++), icu4c (libicu). Find paths via `gcc -print-file-name=libstdc++.so.6` and `icu-config --ldflags`.
