{ pkgs, ... }: {
  packages = [
    pkgs.nodejs_24
    pkgs.uv
    (pkgs.python3.withPackages (python: with python; [
      numpy shapely pyproj requests pillow scipy scikit-image laspy lazrs
    ]))
  ];
}
