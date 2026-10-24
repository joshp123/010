# Reviewed social video

No final clip is currently supplied. Builds keep the existing static JPEG preview
and emit no `og:video` until real media has an accepted review record. A successful
build, codec check or high resolution is not visual acceptance.

## Record and review

1. Use the manager-accepted scene revision and a clean browser view. Let real
   data and assets finish loading; record 10–15 seconds at the intended framing.
   Inspect movement, loading, labels and any visible transport claims throughout.
   Do not manufacture live transport or hide a known rendering defect in the clip.
   Retain the original recording with the review evidence; it must contain no
   personal browser UI or notifications.
2. Prepare a silent H.264 candidate with a poster taken from its actual frames:

   ```sh
   node scripts/prepare-social-video.mjs /path/to/recording.webm FULL_GIT_COMMIT 'https://preview.example/?lat=51.91&lon=4.48&span=280'
   ```

   Requires free `ffmpeg` and `ffprobe`. The default output is
   `work/social-video-candidate/`; the script refuses to overwrite files, retains
   the recording SHA256, adds `@jjpcodes`, and leaves review status `pending`.
   Source commit and URL must identify the scene actually recorded.
3. Watch the resulting MP4 and inspect its JPEG at actual size. Have the manager
   review these artifacts against the accepted scene. Only after acceptance,
   copy `preview.mp4`, `poster.jpg` and `manifest.json` to
   `source-data/social-video/`. Set `review.status` to `accepted`, `reviewedAt` to
   the review date, and `note` to the concrete review decision/evidence location.
   Set an accurate poster alt description. Commit these retained source artifacts.
4. Run `npm run build`. The build verifies SHA256, dimensions, full video decode,
   silent H.264/yuv420p, 2–30 second duration, fast-start MP4 layout and a
   conservative 24 MiB per-file budget. Invalid accepted media fails the build.
   Accepted media is copied into `dist/client/social/` with content-hashed names;
   pending or absent media produces no video tags or copied video.

## Hosting and verification

`public/_headers` supplies media MIME types, inline video disposition, CORS and
immutable caching for hashed media. Cloudflare Workers static assets serve these
files directly; the transit Worker must not intercept them. No fabricated
`Accept-Ranges` header is added: verify actual range responses at the candidate
server after the accepted clip is built and available:

```sh
node scripts/verify-social-video.mjs https://actual-candidate.example
```

The verifier checks the HTML, HTTPS canonical media URLs, JPEG response, MP4 MIME
and length, and a real 1,024-byte range request (`206` + correct `Content-Range`
and MP4 header). It substitutes the candidate origin for canonical asset URLs so
preview verification does not accidentally test old production assets. Exit code
2 means static fallback only; it is not a successful final-video verification.
Repeat on production only after separately authorized publication.

The generated Open Graph metadata includes `og:video`, `secure_url`, `type`,
`width`, `height` and an actual matching poster. `summary_large_image` remains the
static fallback. Metadata does not guarantee video playback on any particular
social platform; this is not an X Player Card integration. If acceptance is
revoked, change status to pending and rebuild to remove the generated assets and
restore the original poster.

References: [Open Graph protocol](https://ogp.me/),
[Workers static asset headers](https://developers.cloudflare.com/workers/static-assets/headers/).
