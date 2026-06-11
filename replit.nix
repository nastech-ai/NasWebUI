{pkgs}: {
  deps = [
    pkgs.glibc
    pkgs.patchelf
    pkgs.dotnet-runtime
    pkgs.gcc
    pkgs.icu
  ];
}
