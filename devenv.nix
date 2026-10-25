{ pkgs, ... }: {
  packages = [
    pkgs.meshoptimizer
    pkgs.nodejs_24
    pkgs.playwright-driver.browsers
    (pkgs.python3.withPackages (python: with python; [
      numpy shapely pyproj requests pillow scipy scikit-image trimesh pygltflib playwright
    ]))
  ];
  env.PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
  env.PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
  env.PROJ_NETWORK = "ON";
}
