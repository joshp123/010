# 010

Rotterdam in miniature. An explorable isometric view of the entire municipality, from the city centre to Hoek van Holland and the Maasvlakte.

Real municipal 3D geometry provides the buildings, bridges, trees and streets. Sunlight, illustrated night lighting and current weather bring the model to life. Share a location or export an image for a post.

## Run locally

No package installation or build step is required:

```sh
python3 -m http.server 8780 --directory dist
```

Open `http://localhost:8780`. A WebGL2-capable browser and an internet connection are needed: detailed geometry streams directly from Rotterdam's public service. Large raw downloads and development captures belong in ignored `work/`.

## Sources and design

- [Data sources and licences](docs/data-sources.md)
- [NYC and London reference inventory](docs/reference-inventory.md)
- [Product requirements and user steering](requirements/README.md)

Code is MIT. Geographic data, weather data and vendored libraries retain their own licences and attribution. Night window patterns are an illustration, not measured interior or occupancy information. Building geometry reflects the source survey dates, not a live reconstruction.

## Hosting

Deployment targets ChatGPT Sites at [010.jjpcodes.com](https://010.jjpcodes.com). Its source identity is retained in `.openai/hosting.json`. The public source repository is [joshp123/010](https://github.com/joshp123/010).

The coordinate-based viewer can be linked from other experiences. This public project contains public city data only.
